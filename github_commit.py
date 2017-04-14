from datetime import datetime

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
