pipeline {
    agent {
        node {
            label 'primary'
        }
    }
    options {
        timestamps()
        disableConcurrentBuilds()
    }
    environment {
        RUNNER_IBCONNECTION = "/F./InfoBase1"
        RUNNER_LANGUAGE = "ru"
        RUNNER_LOCALE = "ru_RU"
        RUNNER_v8version = "8.3.14.1630"
        V83PATH = "C:\\Program Files\\1cv8\\8.3.14.1630\\bin\\1cv8.exe"
        CONFIGURATION_VERSION = ""
    }
    stages {
        stage('test') {
            environment {
                RUNNER_DBUSER = ""
            }
            steps {
                timeout(120) {
                    bat '''@chcp 65001
                    vrunner vanessa --settings scripts\\config\\vrunner_bdd.json
                    '''
                }
            }
        }

    }
}
