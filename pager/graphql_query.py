
import textwrap

#######################################################################################

class GraphQL_Query:


    @staticmethod
    def constructCommitsQuery(organization, repo, ref_time, pagesize, branch='master', cursor=None):
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
            """  % (organization, repo, branch, pagesize, ref_time, cursor_clause)
        return textwrap.dedent(query[1:])


    @staticmethod
    def constructRepoActivityQuery(organization, ref_time, pagesize, commit_count, branch='master', cursor=None):
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
            """ % (pagesize, organization, ref_time, branch, commit_count, ref_time)

        commit_spec     = GraphQL_Query._commitSpec(ref_time, commit_count)[9:]
        repository_spec = GraphQL_Query._repositorySpec(branch)[8:]
        search_spec     = GraphQL_Query._repoSearchSpec(organization, ref_time, branch, 100)
        full_repo_spec  = repository_spec.replace('<< commit_spec >>',        commit_spec)
        full_query      =     search_spec.replace('<< repository_spec >>', full_repo_spec)
        return "{%s\n}" % textwrap.indent(full_query, '  ')

    @staticmethod
    def _repoSearchSpec(owner, ref_time, branch, count, cursor=None):
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

    @staticmethod
    def _repositorySpec(branch):
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

    @staticmethod
    def _commitSpec(ref_time, count):
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
