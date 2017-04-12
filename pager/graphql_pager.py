import json
import requests
import yaml
from datetime import datetime, timedelta
import time
from collections import OrderedDict
from pprint import pprint
import re
import sys

def pretty(data):
    for repo in data:
        for name, info in repo.items():
            print(name)
            for key, value in info.items():
                if value.__class__.__name__ == 'list':
                    print("    %s:" % key)
                    for val in value:
                        if key == 'commits':
                            for k, v in val.items():
                                print("        %s: %s" % (k, val[k]))
                        else:
                            print("        %s" % val)
                        print("        ...")
                else:
                    print("    repo last updated (%s): %s" % (key, info[key]))
            print("___________________")


class Pager:
    def __init__(self, config):
        self.readConfig(config)

        self.all        = []
        self.repo_cursor   = None
        self.commit_cursor = None
        self.last_id        = ''
        self.last_commit_id = ''
        self.repos_next_page   = True
        self.commits_next_page = True
        self.repositoryCount = 0
        self.repo_commit_shas = {}

    def readConfig(self, config):
        with open(config, 'r') as file:
            conf = yaml.load(file)
        github = conf['Github']

        self.organization = github['organization']
        self.pagesize     = github['pagesize']
        self.url          = github['server']
        self.user         = github['user']
        self.token        = github['token']
        self.lookback     = github['lookback']


    def constructRepoQuery(self):
        if not self.repo_cursor:
            query = "{search(first: %s, type: REPOSITORY, query: \"user:%s pushed:>2017-04-10T06:00:00Z\"){" \
                    "edges {node {... on Repository{" \
                    "id name pushedAt ref(qualifiedName:\"master\"){" \
                    "target{... on Commit{history(first:3, since:\"2017-04-10T06:00:00Z\"){" \
                    "edges{node{message oid committer{name} committedDate tree{entries{name}} }}}}}}}}" \
                    "cursor}pageInfo{hasNextPage}repositoryCount}}" \
                    % (self.pagesize, self.organization)
        else:
            query = "{search(first: %s, after: \"%s\", type: REPOSITORY, query: \"user:%s pushed:>2017-04-10T06:00:00Z\"){" \
                    "edges {node {... on Repository{" \
                    "id name pushedAt ref(qualifiedName:\"master\"){" \
                    "target{... on Commit{history(first:3, since:\"2017-04-10T06:00:00Z\"){" \
                    "edges{node{message oid committer{name} committedDate tree{entries{name}} }}}}}}}}" \
                    "cursor}pageInfo{hasNextPage}repositoryCount}}" \
                    % (self.pagesize, self.repo_cursor, self.organization)


        return query


    def constructCommitsQuery(self, repo):
        if not self.commit_cursor:
            query = "{repository(owner: \"%s\", name: \"%s\") {" \
                    "... on Repository{ref(qualifiedName:\"master\"){" \
                    "target{... on Commit{history(first:%s,since:\"2017-04-10T06:00:00Z\"){" \
                    "edges{node{oid id}cursor}pageInfo{hasNextPage}}}}}}}}" \
                     % (self.organization, repo, self.pagesize)
        else:
            query = "{repository(owner: \"%s\", name: \"%s\") {" \
                    "... on Repository{ref(qualifiedName:\"master\"){" \
                    "target{... on Commit{history(first:%s,since:\"2017-04-10T06:00:00Z\", after: \"%s\"){" \
                    "edges{node{oid id}cursor}pageInfo{hasNextPage}}}}}}}}" \
                    % (self.organization, repo, self.pagesize, self.commit_cursor)

        return query

    def madConstructQuery(self, branch, ref_time):
        """
            construct a GraphQL compliant query to specify commits in repos that happened since a specific time.

            Is it possible to use an OrderedDict, push keys/vals in at the appropriate levels and then turn into
            JSON via json.load().dump() ?
        """
        query = """\
              {search(first: %s, type: REPOSITORY, query: "user:%s pushed:>2015-04-05T06:00:00Z"){
                edges {node {
                ... on Repository{
                id name pushedAt ref(qualifiedName:"master"){
                target{
                ... on Commit{history(first:3, since:"2015-04-05T06:00:00Z"){
                edges{node{message oid committer{name} committedDate tree{entries{name}} }}}}}}}}
                cursor}pageInfo{hasNextPage}repositoryCount}} """ % (self.pagesize, self.organization)

        paging_info = 'after: "%s",' % (self.cursor) if self.cursor else ''
        qd = {}
        qd['search'] = 'search(first: %s, %s type: REPOSITORY, query: \"user:%s pushed:>%s\")' % (self.pagesize, paging_info, self.organization, self.lookback)
        qd['repositories'] = 'edges {node {... on Repository{'
        ed = {'node' : ''}
        qd['foop']   = []
        return json.dumps(qd)

    def graphQL_commitSpec(self, count, ref_time):
        commit_spec = \
        """
            target
            {
              ... on Commit
              {
                history(first:%d, since:"%s")
                {
                  edges
                  {
                    node  { oid message committer {name date} committedDate tree {entries {name}} }
                    cursor
                  }
                  pageInfo  { hasNextPage }
                }
              }
            }
        """
        return commit_spec % (count, ref_time)


    def repoCommits(self, repo):
        zero_commits = []
        levels = ['ref', 'target', 'history', 'edges']
        struct = repo
        for level in levels:
            if struct.get(level, None):
                struct = struct[level]
            else:
                return zero_commits
        return struct   # if we're here then all the levels are present and at the end it is a list of None or some commits


    def validateCommitStructure(self, result):
        zero_commits = []
        levels = ['data','repository','ref','target','history']
        struct = result
        for level in levels:
            if struct.get(level, None):
                struct = struct[level]
            else:
                return zero_commits
        return struct

    def getCommitInfo(self, commit_node):
        commit = OrderedDict()
        commit['date'] = commit_node['committedDate']
        commit['sha']  = commit_node['oid']
        commit['committer'] = commit_node['committer']['name']
        if commit_node.get('message', False):
            commit['message'] = commit_node['message']
        else:
            commit['message'] = ""

        if commit_node.get('tree', False) and commit_node['tree'].get('entries', False):
            files = [file['name'] for file in commit_node['tree']['entries']]
            files = ', '.join(f for f in files)
            commit['files'] = files
        else:
            commit['files'] = []
        return commit


    def getCommitsPage(self, repo, repo_commits):
        while self.commits_next_page:
            query = self.constructCommitsQuery(repo)
            result = requests.post(self.url, json.dumps({"query": query}), auth=(self.user, self.token))
            r = result.json()
            r = self.validateCommitStructure(r)
            commits = r['edges']
            self.last_commit_id = commits[-1]['node']['id']
            self.commits_next_page = r['pageInfo']['hasNextPage']
            for commit in commits:
                pprint('repo: %s  commits: %s' % (repo, commit['node']['oid']))
                repo_commits.append(commit['node']['oid'])
                if commit['node']['id'] == self.last_commit_id and self.commits_next_page:
                    self.commit_cursor = commit['cursor']
                    self.getCommitsPage(repo, repo_commits)

    def resetCommitsPageDefaults(self):
        self.commits_next_page = True
        self.commit_cursor     = None

    def processARepo(self, repo):
        repo = repo['node']
        #repo_node = OrderedDict({repo['name']: {'pushedAt': repo['pushedAt']}})
        commits = self.repoCommits(repo)
        if not commits:
            print("THERE ARE NO COMMITS!!!!!!!!")
            return

        commits = []
        self.getCommitsPage(repo['name'], commits)
        self.resetCommitsPageDefaults()

        return commits


    def getRepoPage(self):
        while self.repos_next_page:
            query = self.constructRepoQuery()
            #query = self.madConstructQuery(ref_time)
            response = requests.post(self.url, json.dumps({"query": query}), auth=(self.user, self.token))
            r = response.json()['data']['search']

            #pprint (r['edges'], indent=2, width=220)

            self.repositoryCount = r['repositoryCount']  # should be the same on all pages, this is the total count for the query
            repositories = r['edges']  # these are repositories mentioned on this specific page
            self.last_id = repositories[-1]['node']['id']

            self.repos_next_page = r['pageInfo']['hasNextPage']  # on the last page this will be False

            for repo in repositories:
                #if self.processThisRepo(repo['node']['name'])
                if repo['node']['name'] != "database_connector":
                    #self.repo_commit_shas[repo['node']['name']] = []
                    commits = self.processARepo(repo)
                    self.repo_commit_shas[repo['node']['name']] = commits

                if repo['node']['id'] == self.last_id and self.repos_next_page:
                    print("cursor: %s" % repo['cursor'])
                    sys.stdout.flush()
                    self.repo_cursor = repo['cursor']
                    self.getRepoPage()

    def inflateCommits(self):
        commit_endpoint = "repos/<org_name>/<repo_name>/commits/<sha>"
        github = "https://api.github.com/"
        for repo_name, shas in self.repo_commit_shas.items():
            for sha in shas:
                commit_url = commit_endpoint.replace('<org_name>', self.organization).replace('<repo_name>', repo_name).replace('<sha>', sha)
                full_url = github + commit_url
                response = requests.get(full_url, auth=(self.user, self.token))
                ghc = GithubCommit(response, repo_name, sha)
                if ghc.status == 403:
                    print("Request denied: RateLimit: %s  Remaining:%s  RateReset: %s" % (ghc.rate_limit, ghc.remaining, ghc.reset_time))
                elif ghc.status != 200:
                    print("You bonehead!  You goofed up the request...")
                else:
                    print(ghc)
                sys.stdout.flush()



class GithubCommit:
    def __init__(self, response, repo_name, sha):
        self.sha = sha
        self.repo_name = repo_name
        self.status = response.status_code

        if response.status_code in [200, 403]:
            store = response.headers._store
            self.rate_limit = store['x-ratelimit-limit'][1]
            self.remaining = store['x-ratelimit-remaining'][1]
            reset_time = store['x-ratelimit-reset'][1]
            self.reset_time = datetime.fromtimestamp(int(reset_time))

        if response.status_code == 200:
            result = response.json()
            commit_info = result['commit']
            committer = commit_info['committer']
            self.timestamp = committer['date']
            self.committer = (committer['name'], committer['email'])
            self.message   = commit_info['message']
            self.involved_files = [(file['status'], file['filename']) for file in result['files']]

    def __str__(self):
        return "%s - %s %s %s %s %s" % (self.repo_name, self.sha, self.timestamp, repr(self.committer), self.message[:50], repr(self.involved_files))


config = "configs/test.yml"
pager = Pager(config)


pager.getRepoPage()
pager.inflateCommits()

print("Repository Count: %s" % pager.repositoryCount)
#pretty(pager.all)


