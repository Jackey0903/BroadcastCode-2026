"""AgentCore HTTP entry: backwards-compatible readiness plus tool-driven stories."""

import os

from readiness_agent import MODEL_ID, REGION, ReadinessAgent, ValidationError, make_server
from story_agent import StoryAgent
from story_contract import StoryValidationError
from narration_agent import NarrationAgent


class ProductAgent:
    def __init__(self, bucket, s3, bedrock, expected_bucket_owner=None, model_id=MODEL_ID):
        self.readiness = ReadinessAgent(bucket, s3, bedrock, expected_bucket_owner)
        self.story = StoryAgent(bucket, s3, bedrock, model_id, expected_bucket_owner)
        self.narration = NarrationAgent(self.story)

    def run(self, payload):
        if not isinstance(payload, dict) or payload.get("mode", "readiness") not in ("readiness", "story", "narration"):
            raise ValidationError("mode must be readiness, story or narration")
        if payload.get("mode") == "narration":
            return self.narration.run(payload)
        if payload.get("mode") == "story":
            try:
                return self.story.run(payload)
            except StoryValidationError as error:
                raise ValidationError(str(error)) from error
        return self.readiness.run(payload)


def main():
    import boto3
    from botocore.config import Config

    bucket = os.environ.get("READINESS_BUCKET", "")
    if not bucket:
        raise RuntimeError("READINESS_BUCKET must be set")
    config = Config(connect_timeout=8, read_timeout=55, retries={"total_max_attempts": 1})
    agent = ProductAgent(bucket, boto3.client("s3", region_name=REGION, config=config),
                         boto3.client("bedrock-runtime", region_name=REGION, config=config),
                         os.environ.get("READINESS_BUCKET_OWNER"), os.environ.get("MODEL_ID", MODEL_ID))
    make_server(agent).serve_forever()


if __name__ == "__main__":
    main()
