// PACE Daily Cycle — Jenkinsfile (Declarative Pipeline)
//
// This file is managed by PACE ci_generator.py.
// To change the schedule, update the `cron:` section in pace/pace.config.yaml
// and run:  python pace/ci_generator.py --apply
//
// Required Jenkins Credentials (Manage Jenkins → Credentials):
//   ANTHROPIC_API_KEY   — Secret text, ID: "anthropic-api-key"
//
// Required Jenkins Properties (global or pipeline-level):
//   PACE_DAY            — current sprint day number
//
// Optional Jenkins Properties:
//   PACE_PAUSED         — "true" to pause the loop after a HOLD
//   PACE_DAILY_BUDGET   — daily cost cap in USD (e.g. "5.00"; 0 or empty = no cap)
//   PACE_DAILY_SPEND    — accumulated daily spend (persisted in jenkins-variables.json)
//   PACE_REPORTER_TIMEZONE — IANA timezone (default: "UTC")

pipeline {
    agent {
        docker {
            image 'python:3.12-slim'
            args '--user root'
        }
    }

    // Edit the schedule in pace/pace.config.yaml → cron.pace_pipeline, then
    // run: python pace/ci_generator.py --apply  to regenerate this file.
    triggers {
        cron('0 9 * * 1-5')
    }

    options {
        timeout(time: 90, unit: 'MINUTES')
        disableConcurrentBuilds()
    }

    environment {
        ANTHROPIC_API_KEY = credentials('anthropic-api-key')
        JENKINS_URL_ENV   = "${JENKINS_URL}"
        JENKINS_USER      = credentials('jenkins-api-user')
        JENKINS_TOKEN     = credentials('jenkins-api-token')
        JENKINS_JOB_NAME  = "${JOB_NAME}"
    }

    stages {
        stage('Setup') {
            steps {
                sh '''
                    git config user.name "PACE Orchestrator"
                    git config user.email "pace@jenkins.local"
                    pip install -r pace/requirements.txt --quiet
                '''
            }
        }

        stage('Validate Config') {
            steps {
                sh 'python pace/config_tester.py --strict'
            }
        }

        stage('Budget Check') {
            steps {
                script {
                    def budget = env.PACE_DAILY_BUDGET ?: '0'
                    def spend  = env.PACE_DAILY_SPEND  ?: '0'
                    def tz     = env.PACE_REPORTER_TIMEZONE ?: 'UTC'
                    def today  = sh(script: "TZ='${tz}' date +%Y-%m-%d", returnStdout: true).trim()
                    if (env.PACE_DAILY_SPEND_DATE != today) {
                        spend = '0'
                        writeFile file: 'jenkins-variables.json',
                                  text: groovy.json.JsonOutput.toJson([PACE_DAILY_SPEND: '0', PACE_DAILY_SPEND_DATE: today])
                    }
                    env.PACE_SPEND_TODAY = spend
                    if (budget != '0' && budget) {
                        def exceeded = sh(
                            script: "python3 -c \"import sys; sys.exit(0 if float('${spend}') >= float('${budget}') else 1)\"",
                            returnStatus: true
                        ) == 0
                        if (exceeded) {
                            echo "[PACE] Daily budget \$${budget} reached (\$${spend} today). Skipping."
                            currentBuild.result = 'NOT_BUILT'
                            return
                        }
                    }
                }
            }
        }

        stage('PACE Cycle') {
            when {
                expression { currentBuild.result != 'NOT_BUILT' }
            }
            steps {
                sh 'python pace/orchestrator.py'
            }
        }
    }

    post {
        always {
            archiveArtifacts artifacts: '.pace/**,PROGRESS.md,jenkins-summary.md,jenkins-variables.json',
                             allowEmptyArchive: true
        }
        failure {
            script {
                def day = env.PACE_DAY ?: '1'
                def escalated = fileExists(".pace/day-${day}/escalated")
                if (escalated) {
                    def vars = [:]
                    try {
                        vars = readJSON file: 'jenkins-variables.json'
                    } catch (e) {}
                    vars.PACE_PAUSED = 'true'
                    writeFile file: 'jenkins-variables.json',
                              text: groovy.json.JsonOutput.toJson(vars)
                    echo "[PACE] PACE_PAUSED set to true (escalated HOLD)."
                }
            }
        }
    }
}
