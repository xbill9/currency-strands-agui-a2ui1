#!/usr/bin/env bash
# Build the Next.js UI, push it to ECR and run it on ECS Express Mode, pointed at
# the agent on AgentCore Runtime. Re-running updates the service in place.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REGION="${AWS_REGION:-$(aws configure get region)}"
ACCOUNT="$(aws sts get-caller-identity --query Account --output text)"
SERVICE="${UI_SERVICE:-currency-strands-ui}"
ECR_REPO="${ECR_REPO:-currency-strands-ui}"
TASK_ROLE="${UI_TASK_ROLE:-currency-strands-ui-task}"
TAG="$(git -C "$REPO_ROOT" rev-parse --short HEAD 2>/dev/null || date +%s)"

RUNTIME_ARN="$(cd "$REPO_ROOT" && agentcore status --json 2>/dev/null |
  python3 -c 'import json,sys; print(next(r["arn"] for r in json.load(sys.stdin)["resources"] if r["resourceType"]=="runtime"))')"
echo "AgentCore runtime: $RUNTIME_ARN"

echo "=== 1/4 ECR repository and image ==="
aws ecr describe-repositories --repository-names "$ECR_REPO" --region "$REGION" >/dev/null 2>&1 ||
  aws ecr create-repository --repository-name "$ECR_REPO" --region "$REGION" \
    --image-scanning-configuration scanOnPush=true >/dev/null
REGISTRY="$ACCOUNT.dkr.ecr.$REGION.amazonaws.com"
IMAGE="$REGISTRY/$ECR_REPO:$TAG"
aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "$REGISTRY" >/dev/null
docker build --platform linux/amd64 -t "$IMAGE" "$REPO_ROOT/frontend-react"
docker push "$IMAGE"

echo "=== 2/4 task role: may invoke this one AgentCore runtime ==="
if ! aws iam get-role --role-name "$TASK_ROLE" >/dev/null 2>&1; then
  aws iam create-role --role-name "$TASK_ROLE" --assume-role-policy-document '{
    "Version": "2012-10-17",
    "Statement": [{"Effect": "Allow", "Principal": {"Service": "ecs-tasks.amazonaws.com"},
                   "Action": "sts:AssumeRole"}]}' >/dev/null
fi
aws iam put-role-policy --role-name "$TASK_ROLE" --policy-name invoke-agentcore-runtime \
  --policy-document "{
    \"Version\": \"2012-10-17\",
    \"Statement\": [{\"Effect\": \"Allow\", \"Action\": \"bedrock-agentcore:InvokeAgentRuntime\",
                     \"Resource\": [\"$RUNTIME_ARN\", \"$RUNTIME_ARN/*\"]}]}"

echo "=== 3/4 ECS Express Mode service ==="
CONTAINER="{
  \"image\": \"$IMAGE\",
  \"containerPort\": 3000,
  \"environment\": [
    {\"name\": \"AGENTCORE_RUNTIME_ARN\", \"value\": \"$RUNTIME_ARN\"},
    {\"name\": \"AWS_REGION\", \"value\": \"$REGION\"}
  ]
}"
EXISTING="$(aws ecs describe-express-gateway-service --service-arn \
  "arn:aws:ecs:$REGION:$ACCOUNT:service/default/$SERVICE" --region "$REGION" \
  --query 'service.status.statusCode' --output text 2>/dev/null || true)"
if [[ "$EXISTING" == "ACTIVE" ]]; then
  aws ecs update-express-gateway-service --region "$REGION" \
    --service-arn "arn:aws:ecs:$REGION:$ACCOUNT:service/default/$SERVICE" \
    --primary-container "$CONTAINER" >/dev/null
else
  aws ecs create-express-gateway-service --region "$REGION" \
    --service-name "$SERVICE" \
    --execution-role-arn "arn:aws:iam::$ACCOUNT:role/ecsTaskExecutionRole" \
    --infrastructure-role-arn "arn:aws:iam::$ACCOUNT:role/ecsInfrastructureRoleForExpressServices" \
    --task-role-arn "arn:aws:iam::$ACCOUNT:role/$TASK_ROLE" \
    --health-check-path / \
    --cpu 1024 --memory 2048 \
    --scaling-target '{"minTaskCount": 1, "maxTaskCount": 2}' \
    --primary-container "$CONTAINER" >/dev/null
fi

echo "=== 4/4 endpoint ==="
aws ecs describe-express-gateway-service --region "$REGION" \
  --service-arn "arn:aws:ecs:$REGION:$ACCOUNT:service/default/$SERVICE" \
  --query 'service.activeConfigurations[0].ingressPaths[0].endpoint' --output text
