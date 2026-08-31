"""테스트에서 github_sync 를 '설정된' 상태로 만드는 공용 override 값."""

ENABLED_SETTINGS = dict(
    GITHUB_OAUTH_CLIENT_ID="test-client-id",
    GITHUB_OAUTH_CLIENT_SECRET="test-secret",
    GITHUB_TOKEN_ENC_KEY="RWImiVVz7DAul0Cm4lFn1NlLmRpVsS3InrjkNx7nuW4=",
    GITHUB_SUBMISSION_REPO_NAME="lms-assignments",
    DEV_SKIP_AUTH=False,
)
