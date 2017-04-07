import json
import requests
import yaml

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


    def constructQuery(self):
        if not self.cursor:
            query = "{search(first: %s, type: REPOSITORY, query: \"user:%s pushed:>2017-04-05T06:00:00Z\"){" \
                    "edges {node {... on Repository{" \
                    "id name pushedAt ref(qualifiedName:\"master\"){" \
                    "target{... on Commit{history(first:3, since:\"2017-04-05T06:00:00Z\"){" \
                    "edges{node{message committer{name date}}}}}}}}}" \
                    "cursor}pageInfo{hasNextPage}repositoryCount}}" \
                    % (self.pagesize, self.organization)
        else:
            query = "{search(first: %s, after: \"%s\", type: REPOSITORY, query: \"user:%s pushed:>2017-04-05T06:00:00Z\"){" \
                    "edges {node {... on Repository{" \
                    "id name pushedAt ref(qualifiedName:\"master\"){" \
                    "target{... on Commit{history(first:3, since:\"2017-04-05T06:00:00Z\"){" \
                    "edges{node{message committer{name date}}}}}}}}}" \
                    "cursor}pageInfo{hasNextPage}repositoryCount}}" \
                    % (self.pagesize, self.cursor, self.organization)
        return query



    def getPage(self):
        while self.next_page:
            query = self.constructQuery()
            result = requests.post(self.url, json.dumps({"query": query}), auth=(self.user, self.token))
            r = result.json()['data']['search']
            self.repositoryCount = r['repositoryCount']
            repositories = r['edges']
            self.next_page = r['pageInfo']['hasNextPage']

            for repo in repositories:
                self.last_id = repositories[-1]['node']['id']
                repo_commits = []
                self.all.append({repo['node']['name']: {'pushedAt': repo['node']['pushedAt'], 'commits': repo_commits}})
                commits = repo['node']['ref']['target']['history']['edges']
                for commit in commits:
                    repo_commits.append({'message': commit['node']['message'],
                                         'committer': commit['node']['committer']['name'],
                                         'date': commit['node']['committer']['date']})

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