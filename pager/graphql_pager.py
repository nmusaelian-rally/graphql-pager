import json
import requests
import yaml
from collections import OrderedDict
from pprint import pprint

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
            query = "{search(first: %s, type: REPOSITORY, query: \"user:%s pushed:>2015-04-05T06:00:00Z\"){" \
                    "edges {node {... on Repository{" \
                    "id name pushedAt ref(qualifiedName:\"master\"){" \
                    "target{... on Commit{history(first:3, since:\"2015-04-05T06:00:00Z\"){" \
                    "edges{node{message oid committer{name} committedDate tree{entries{name}} }}}}}}}}" \
                    "cursor}pageInfo{hasNextPage}repositoryCount}}" \
                    % (self.pagesize, self.organization)
        else:
            query = "{search(first: %s, after: \"%s\", type: REPOSITORY, query: \"user:%s pushed:>2015-04-05T06:00:00Z\"){" \
                    "edges {node {... on Repository{" \
                    "id name pushedAt ref(qualifiedName:\"master\"){" \
                    "target{... on Commit{history(first:3, since:\"2015-04-05T06:00:00Z\"){" \
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
        paging_info = 'after: "%s",' % () if self.cursor else ''
        qd = {}
        qd['search'] = 'search(first: %s, %s type: REPOSITORY, query: \"user:%s pushed:>%s\")' % (self.pagesize, paging_info, self.organization, self.lookback)
        ed = {'node' : ''}
        qd['foop']   = []
        return json.dumps(qd)






    def getPage(self):
        while self.next_page:
            query = self.constructQuery()
            result = requests.post(self.url, json.dumps({"query": query}), auth=(self.user, self.token))
            r = result.json()['data']['search']
            pprint (r)
            self.repositoryCount = r['repositoryCount']
            repositories = r['edges']
            self.next_page = r['pageInfo']['hasNextPage']

            for repo in repositories:
                self.last_id = repositories[-1]['node']['id']
                repo_commits = []
                repo_node = OrderedDict({repo['node']['name']: {'pushedAt': repo['node']['pushedAt'], 'commits': repo_commits}})
                #reop_node['node'] =

                self.all.append(repo_node)
                commits = repo['node']['ref']['target']['history']['edges']
                for commit in commits:

                    commit_node = OrderedDict()
                    #commit_node['date']      = commit['node']['committer']['date']
                    commit_node['date']      = commit['node']['committedDate']
                    commit_node['sha']       = commit['node']['oid']
                    commit_node['committer'] = commit['node']['committer']['name']
                    commit_node['message']   = commit['node']['message']
                    files = [file['name'] for file in commit['node']['tree']['entries']]
                    files = ', '.join(f for f in files)
                    commit_node['files']     = files
                    repo_commits.append(commit_node)

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