#!/bin/bash

set -euo pipefail

# Deploy main app
APP_DIR=/var/www/${PROJECT_ID}
APP_DOCKER_IMAGE=cfranklin11/tipresias_backend:latest
PORT=80
CI=${CI:-""}


if [ "${CI}" ]
then
  sudo chmod 600 ~/.ssh/deploy_rsa
  sudo chmod 755 ~/.ssh
fi

echo "Deploying main app to DigitalOcean..."

scp -i ~/.ssh/deploy_rsa -oStrictHostKeyChecking=no \
  docker-compose.prod.yml \
  ${DIGITAL_OCEAN_USER}@${PRODUCTION_HOST}:${APP_DIR}/docker-compose.yml

RUN_APP="
  cd ${APP_DIR} \
    && docker pull ${APP_DOCKER_IMAGE} \
    && docker-compose stop \
    && docker-compose up -d
"

# We use 'ssh' instead of 'doctl compute ssh' to be able to bypass key checking.
ssh -i ~/.ssh/deploy_rsa -oStrictHostKeyChecking=no \
  ${DIGITAL_OCEAN_USER}@${PRODUCTION_HOST} \
  ${RUN_APP}

if [ $? != 0 ]
then
  exit $?
fi

./scripts/wait-for-it.sh ${PRODUCTION_HOST}:${PORT} \
  -t 60 \
  -- ./scripts/post_deploy.sh

echo "Main app deployed!"

# Deploy tipping service
echo "Deploying serverless functions..."

SERVICE_DOCKER_IMAGE=cfranklin11/${PROJECT_ID}_tipping:latest
TIPPING_CONTAINER=tipping

# Need lots of deploy-specific env vars, so we use docker instead of docker-compose
docker run \
  -v ${HOME}/.aws:/app/.aws \
  -e AWS_SHARED_CREDENTIALS_FILE=".aws/credentials" \
  -e DATABASE_HOST='db.fauna.com' \
  -e DATA_SCIENCE_SERVICE=${DATA_SCIENCE_SERVICE} \
  -e DATA_SCIENCE_SERVICE_TOKEN=${DATA_SCIENCE_SERVICE_TOKEN} \
  -e FAUNA_SECRET=${FAUNA_SECRET} \
  -e FOOTY_TIPS_USERNAME=${FOOTY_TIPS_USERNAME} \
  -e FOOTY_TIPS_PASSWORD=${FOOTY_TIPS_PASSWORD} \
  -e MONASH_USERNAME=${MONASH_USERNAME} \
  -e MONASH_PASSWORD=${MONASH_PASSWORD} \
  -e ROLLBAR_TOKEN=${ROLLBAR_TOKEN} \
  -e SPLASH_SERVICE=${SPLASH_SERVICE} \
  -e TIPPING_SERVICE_TOKEN=${TIPPING_SERVICE_TOKEN} \
  -e TIPRESIAS_APP=${TIPRESIAS_APP} \
  -e TIPRESIAS_APP_TOKEN=${TIPRESIAS_APP_TOKEN} \
  --name ${TIPPING_CONTAINER} \
  ${SERVICE_DOCKER_IMAGE} \
  /bin/bash -c "npx sls deploy && alembic upgrade head"

echo "Serverless functions deployed!"
