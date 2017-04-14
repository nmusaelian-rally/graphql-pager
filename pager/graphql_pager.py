import sys
from datetime    import datetime, timedelta
from collections import OrderedDict
import json
import re
import textwrap
from pprint import pprint

import yaml
import requests

######################################################################################

INCLUSIONS = ['alm*', '*eif*', '*connect*', '*web*', 'rally*', '*spok*', 'redpi*']
EXCLUSIONS = ['georgetest*', 'connortest*', 'clitest*']

#######################################################################################

def main(args):

    config = "configs/verglas.yml"
    pager = Pager(config)

    pager.processActiveRepositories('2017-04-11T07:00:30Z', 10)
    pager.inflateCommits()

    print("Repository Count: %s" % pager.repositoryCount)
    print("Qualified Repositories:")
    for repo in sorted(pager.qualified_repositories):
        print("    %s" % repo)
    print("\n")
    print("DISQualified Repositories:")
    for repo in sorted(pager.disqualified_repositories):
        print("    %s" % repo)

#######################################################################################

class Pager:
    def __init__(self, config):
        self.readConfig(config)

        self.repo_cursor   = None
        self.commit_cursor = None
        self.last_id        = ''
        self.last_commit_id = ''
        self.next_repos_page   = True
        self.next_commits_page = True
        self.repositoryCount = 0
        self.repo_commit_shas = {}
        self.qualified_repositories    = []
        self.disqualified_repositories = []

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

    def altConstructCommitsQuery(self, repo, ref_time, branch='master', cursor=None):
        """
            construct a GraphSQL compliant query to get commit related info for commits
            that were done past a specific time on a specific branch.
        """
        cursor_clause = ', after: "%s"' % cursor if cursor else ''
        query = \
            """
            { repository(owner: "%s", name: "%s") {
                ... on Repository {
                  ref(qualifiedName:"%s") {
                    target {
                      ... on Commit {
                        history(first:%s,since:"%s"%s) {
                          edges {
                            node {oid id}
                            cursor
                          }
                          pageInfo{hasNextPage}
                        }
                      }
                    }
                  }
                }
              }
            }
            """  % (self.organization, repo, branch, self.pagesize, ref_time, cursor_clause)
        return textwrap.dedent(query[1:])


    def altConstructQuery(self, ref_time, commit_count, branch='master', cursor=None):
        """
            construct a GraphQL compliant query to specify commits in repos that happened since a specific time.
        """
        query = \
            """
              {search(first: %s, type: REPOSITORY, query: "user:%s pushed:>%s") {
                edges {
                  node {
                    ... on Repository {
                      id
                      name
                      pushedAt
                      ref(qualifiedName:"%s") {
                        target {
                          ... on Commit {
                            history(first:%d, since:"%s"){
                              edges {
                                node { oid message committer{name} committedDate tree{entries{name}}
                                cursor
                              }
                            }
                          }
                        }
                      }
                     }}}
                     cursor
                  }
                  pageInfo{hasNextPage}
                  repositoryCount
                }
            }
            """ % (self.pagesize, self.organization, ref_time, "master", 10, ref_time)

        commit_spec     = self.graphQL_commitSpec(ref_time, commit_count)[9:]
        repository_spec = self.graphQL_repositorySpec(branch)[8:]
        search_spec     = self.graphQL_repoSearchSpec(self.organization, ref_time, branch, 100)
        full_repo_spec = repository_spec.replace('<< commit_spec >>', commit_spec)
        full_query = search_spec.replace('<< repository_spec >>', full_repo_spec)
        return "{%s\n}" % textwrap.indent(full_query, '  ')

    def graphQL_repoSearchSpec(self, owner, ref_time, branch, count, cursor=None):
        search_spec = \
        """
        search(first: %d, %s type: REPOSITORY, query: "user:%s pushed:>%s")
        {
          edges
          {
            node
            {
               << repository_spec >>
            }
            cursor
          }
          pageInfo {hasNextPage}
          repositoryCount
        }"""
        cursor_clause = "after: %s, " if cursor else ''
        result = search_spec % (count, cursor_clause, owner, ref_time)
        return textwrap.dedent(result)

    def graphQL_repositorySpec(self, branch):
        repository_spec = \
        """
        ... on Repository
        {
          id
          name
          pushedAt
          ref(qualifiedName:"%s")
          {
            << commit_spec >>
          }
        }"""
        return repository_spec % branch

    def graphQL_commitSpec(self, ref_time, count):
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
                  pageInfo {hasNextPage}
                }
              }
            }"""
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


    # def getCommitInfo(self, commit_node):
    #     """
    #         This method is only relevant for if and when the GraphQL response
    #         for the request to get repositories with commits since a specific time mark
    #         actually sends back accurate information about the files involved in the commit.
    #     """
    #     commit = OrderedDict()
    #     commit['date'] = commit_node['committedDate']
    #     commit['sha']  = commit_node['oid']
    #     commit['committer'] = commit_node['committer']['name']
    #     if commit_node.get('message', False):
    #         commit['message'] = commit_node['message']
    #     else:
    #         commit['message'] = ""
    #
    #     if commit_node.get('tree', False) and commit_node['tree'].get('entries', False):
    #         files = [file['name'] for file in commit_node['tree']['entries']]
    #         files = ', '.join(f for f in files)
    #         commit['files'] = files
    #     else:
    #         commit['files'] = []
    #     return commit


    def getCommitsPage(self, repo, ref_time, repo_commits, cursor=None):
        while self.next_commits_page:
            #query     = self.constructCommitsQuery(repo)
            #response = requests.post(self.url, json.dumps({"query": query}), auth=(self.user, self.token))
            query = self.altConstructCommitsQuery(repo, ref_time, branch='master', cursor=cursor)
            response = requests.post(self.url, json.dumps({"query": query}), auth=(self.user, self.token))
            result = response.json()
            result = self.validateCommitStructure(result)
            commits = result['edges']
            self.last_commit_id = commits[-1]['node']['id']
            self.next_commits_page = result['pageInfo']['hasNextPage']
            for commit in commits:
                pprint('repo: %s  commits: %s' % (repo, commit['node']['oid']))
                repo_commits.append(commit['node']['oid'])
                if commit['node']['id'] == self.last_commit_id and self.next_commits_page:
                    self.commit_cursor = commit['cursor']
                    self.getCommitsPage(repo, ref_time, repo_commits, cursor=commit['cursor'])


    def resetCommitsPageDefaults(self):
        self.next_commits_page = True
        self.commit_cursor     = None

    def processRepositoryCommits(self, repo, ref_time):
        #repo_node = OrderedDict({repo['name']: {'pushedAt': repo['pushedAt']}})
        commits = self.repoCommits(repo)
        if not commits:
            print("THERE ARE NO COMMITS!!!!!!!!")
            return

        commits = []
        self.getCommitsPage(repo['name'], ref_time, commits)
        self.resetCommitsPageDefaults()

        return commits


    def processActiveRepositories(self, ref_time, commit_count, cursor=None):
        while self.next_repos_page:
            #query = self.constructRepoQuery()
            query = self.altConstructQuery(ref_time, commit_count, branch='master')
            response = requests.post(self.url, json.dumps({"query": query}), auth=(self.user, self.token))
            result = response.json()['data']['search']

            #pprint (result['edges'], indent=2, width=220)

            self.repositoryCount = result['repositoryCount']  # should be the same on all pages, this is the total count for the query
            repositories = result['edges']  # these are repositories mentioned on this specific page
            self.last_id = repositories[-1]['node']['id']

            self.next_repos_page = result['pageInfo']['hasNextPage']  # on the last page this will be False

            for repo in repositories:
                repo_name = repo['node']['name']
                if self.qualifiedRepository(repo_name):
                    self.qualified_repositories.append(repo_name)
                    commits = self.processRepositoryCommits(repo['node'], ref_time)
                    self.repo_commit_shas[repo_name] = commits
                else:
                    self.disqualified_repositories.append(repo_name)

                if repo['node']['id'] == self.last_id and self.next_repos_page:
                    #print("cursor: %s" % repo['cursor'])
                    sys.stdout.flush()
                    self.repo_cursor = repo['cursor']
                    self.processActiveRepositories(ref_time, commit_count, cursor=repo['cursor'])


    def qualifiedRepository(self, repo_name):
        qualified = False
        for item in INCLUSIONS:
            if '*' not in item:
                if repo_name == item:
                    qualified = True
            else:
                regex_patt = item.replace('*', r'.*' )
                mo = re.search(regex_patt, repo_name, re.I)
                if mo:
                    qualified = True
            if qualified: break

        if not qualified:
            return False

        for item in EXCLUSIONS:
            if '*' not in item:
                if repo_name == item:
                    qualified = False
                    break
            else:
                regex_patt = item.replace('*', r'.*' )
                mo = re.search(regex_patt, repo_name, re.I)
                if mo:
                    qualified = False
                    break
        return qualified


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


######################################################################################

class GithubCommit:
    def __init__(self, response, repo_name, sha):
        self.sha = sha
        self.repo_name = repo_name
        self.status = response.status_code

        if response.status_code in [200, 403]:
            store = response.headers._store
            self.captureRateLimitInfo(store)

        if response.status_code == 200:
            payload = response.json()
            self.captureCommitInfo(payload)

    def captureRateLimitInfo(self, store):
        self.rate_limit = store['x-ratelimit-limit'][1]
        self.remaining  = store['x-ratelimit-remaining'][1]
        reset_time      = store['x-ratelimit-reset'][1]
        self.reset_time = datetime.fromtimestamp(int(reset_time))

    def captureCommitInfo(self, payload):
        commit_info = payload['commit']
        committer   = commit_info['committer']
        self.timestamp = committer['date']
        self.committer = (committer['name'], committer['email'])
        self.message   = commit_info['message']
        self.involved_files = [(file['status'], file['filename']) for file in payload['files']]

    def __str__(self):
        return "%s - %s %s %s %s %s" % \
               (self.repo_name, self.sha, self.timestamp, repr(self.committer),
                self.message[:50], repr(self.involved_files))

######################################################################################
######################################################################################

if __name__ == '__main__':
    main(sys.argv[1:])

