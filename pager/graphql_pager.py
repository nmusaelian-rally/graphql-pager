import sys, os
import json
import re
from pprint import pprint

import yaml
import requests

from graphql_query import GraphQL_Query
from github_commit import GithubCommit

######################################################################################

INCLUSIONS = ['alm*', '*eif*', '*connect*', '*web*', 'rally*', '*spok*', 'redpi*']
EXCLUSIONS = ['georgetest*', 'connortest*', 'clitest*']

#######################################################################################

def main(args):
    if not args:
        print("ERROR: You must provide the base name of a config file to be found in the configs subdir")
        sys.exit(1)
    conf_name = args.pop(0)

    if conf_name.endswith('.yml'):
        config = "configs/%s" % conf_name
    else:
        config = "configs/%s.yml" % conf_name
    if not os.path.exists(config):
        print("ERROR: unable to find a config file associated with %s" % conf_name)
        sys.exit(2)

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


    def getCommitsPage(self, organization, repo, ref_time, repo_commits, pagesize, cursor=None):
        while self.next_commits_page:
            #query     = self.constructCommitsQuery(repo)
            query = GraphQL_Query.constructCommitsQuery(organization, repo, ref_time, pagesize, branch='master', cursor=cursor)
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
                    self.getCommitsPage(organization, repo, ref_time, repo_commits, pagesize, cursor=commit['cursor'])


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
        COMMITS_PAGE_SIZE = 100
        self.getCommitsPage(self.organization, repo['name'], ref_time, commits, COMMITS_PAGE_SIZE)
        self.resetCommitsPageDefaults()

        return commits


    def processActiveRepositories(self, ref_time, commit_count, cursor=None):
        REPOS_PAGE_SIZE = 100
        while self.next_repos_page:
            #query = self.constructRepoQuery()
            query = GraphQL_Query.constructRepoActivityQuery(self.organization, ref_time, REPOS_PAGE_SIZE, commit_count, branch='master')
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
######################################################################################

if __name__ == '__main__':
    main(sys.argv[1:])

