properties([[$class: 'GitLabConnectionProperty', gitLabConnection: 'figitlab']])

if(env.JOB_NAME =~ 'utils/'){
    node('sudo'){
        env.AMQP_URL="amqp://guest:guest@localhost/"
        env.AMQP_EXCHANGE="amq.topic"

        stage("Clone repo and submodules"){
            checkout scm
            sh '''
                git submodule update --init
                tree .
            '''
        }

        stage ("Environment dependencies"){
            withEnv(["DEBIAN_FRONTEND=noninteractive"]){
                sh '''
                    sudo apt-get clean
                    sudo apt-get update
                    sudo apt-get upgrade -y -qq
                    sudo apt-get install --fix-missing -y -qq python-dev python-pip python-setuptools
                    sudo apt-get install --fix-missing -y -qq python3-dev python3-pip python3-setuptools
                    sudo apt-get install --fix-missing -y -qq build-essential
                    sudo apt-get install --fix-missing -y -qq libyaml-dev
                    sudo apt-get install --fix-missing -y -qq libssl-dev openssl
                    sudo apt-get install --fix-missing -y -qq libffi-dev
                    sudo apt-get install --fix-missing -y -qq curl tree netcat
                    sudo apt-get install --fix-missing -y -qq rabbitmq-server
                    sudo apt-get install --fix-missing -y -qq supervisor
                    sudo apt-get install --fix-missing -y -qq make

                    echo restarting rmq server and app
                    sudo rabbitmq-server -detached || true
                    sudo rabbitmqctl stop_app || true
                    sudo rabbitmqctl start_app || true
                '''

          }
      }

      stage("install dependencies"){
        gitlabCommitStatus("install dependencies"){
            withEnv(["DEBIAN_FRONTEND=noninteractive"]){
            sh '''
                echo installing python dependencies...
                sudo -H python3 -m pip -qq install -r requirements.txt
            '''
            }
        }
      }

      stage("unittesting modules"){
        gitlabCommitStatus("unittesting modules"){
            sh '''
                echo $AMQP_URL
                pwd
                python3 -m pytest -p no:cacheprovider tests
            '''
        }
      }
    }
}

