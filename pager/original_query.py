class GraphQLPager:
    def __init__(self):
        self.readConfig(config)

        self.repo_cursor = None
        self.commit_cursor = None
        self.last_id = ''
        self.last_commit_id = ''
        self.next_repos_page = True
        self.next_commits_page = True
        self.repositoryCount = 0
        self.repo_commit_shas = {}

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