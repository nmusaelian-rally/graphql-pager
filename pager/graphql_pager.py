import json
import requests
import yaml
from collections import OrderedDict
from pprint import pprint
import re

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
        self.cursor     = None
        self.last_id    = ''
        self.next_page  = True
        self.repositoryCount = 0

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


    def constructQuery(self):
        if not self.cursor:
            query = "{search(first: %s, type: REPOSITORY, query: \"user:%s pushed:>2017-04-05T06:00:00Z\"){" \
                    "edges {node {... on Repository{" \
                    "id name pushedAt ref(qualifiedName:\"master\"){" \
                    "target{... on Commit{history(first:3, since:\"2017-04-05T06:00:00Z\"){" \
                    "edges{node{message oid committer{name} committedDate tree{entries{name}} }}}}}}}}" \
                    "cursor}pageInfo{hasNextPage}repositoryCount}}" \
                    % (self.pagesize, self.organization)
        else:
            query = "{search(first: %s, after: \"%s\", type: REPOSITORY, query: \"user:%s pushed:>2017-04-05T06:00:00Z\"){" \
                    "edges {node {... on Repository{" \
                    "id name pushedAt ref(qualifiedName:\"master\"){" \
                    "target{... on Commit{history(first:3, since:\"2017-04-05T06:00:00Z\"){" \
                    "edges{node{message oid committer{name} committedDate tree{entries{name}} }}}}}}}}" \
                    "cursor}pageInfo{hasNextPage}repositoryCount}}" \
                    % (self.pagesize, self.cursor, self.organization)


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


    def repoCommits(self, repo):
        zero_commits = []
        levels = ['node', 'ref', 'target', 'history', 'edges']
        struct = repo
        for level in levels:
            if struct.get(level, None):
                struct = struct[level]
            else:
                return zero_commits
        return struct   # if we're here then all the levels are present and at the end it is a list of None or some commits

    def getCommitInfo(self, commit_node):
        commit = OrderedDict()
        commit['date'] = commit_node['committedDate']
        commit['sha']  = commit_node['oid']
        commit['committer'] = commit_node['committer']['name']
        if commit_node.get('message', False):
            commit['message'] = commit_node['message']
        else:
            commit['message'] = ""

        # levels = ['tree','entries']
        # struct = commit_node
        # for level in levels:
        #     if struct.get(level,None):
        #         struct = struct[level]

        if commit_node.get('tree', False) and commit_node['tree'].get('entries', False):
            files = [file['name'] for file in commit_node['tree']['entries']]
            files = ', '.join(f for f in files)
            commit['files'] = files
        else:
            commit['files'] = []
        return commit

    def getPage(self):
        while self.next_page:
            query = self.constructQuery()
            result = requests.post(self.url, json.dumps({"query": query}), auth=(self.user, self.token))
            r = result.json()['data']['search']

            pprint (r['edges'], indent=2, width=220)

            self.repositoryCount = r['repositoryCount']  # should be the same on all pages, this is the total count for the query
            repositories = r['edges']  # these are repositories mentioned on this specific page

            self.next_page = r['pageInfo']['hasNextPage']  # on the last page this will be False

            for repo in repositories:
                self.last_id = repositories[-1]['node']['id']
                repo_commits = []
                repo_node = OrderedDict({repo['node']['name']: {'pushedAt': repo['node']['pushedAt'], 'commits': repo_commits}})
                commits = self.repoCommits(repo)
                if not commits:
                    continue

                self.all.append(repo_node)
                for commit_struct in commits:
                    commit = self.getCommitInfo(commit_struct['node'])
                    repo_commits.append(commit)

            if repo['node']['id'] == self.last_id and self.next_page:
                print("cursor: %s" % repo['cursor'])
                self.cursor = repo['cursor']
                self.getPage()

config = "configs/test.yml"
pager = Pager(config)
pager.getPage()

print("Repository Count: %s" % pager.repositoryCount)
pretty(pager.all)


print("\nLength of list of repos: %s must be the same as totalCount: %s " %(len(pager.all), pager.repositoryCount))
assert len(pager.all) == pager.repositoryCount