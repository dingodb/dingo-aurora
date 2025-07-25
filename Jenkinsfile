pipeline {
    agent {
        node {
            label "dingo_stack"
        }
    }
    environment {
      SOURCE_DIR = '/data/pipeline_demo'
      BUILD_DATE = sh(script: 'date +%Y%m%d', returnStdout: true).trim()
      IMAGE_TAG = "${branch ? branch : 'main'}-${BUILD_DATE}"
    }
    triggers {
        GenericTrigger (
            causeString: 'Triggered', 
            genericVariables: [
              [key: 'ref', value: '$.ref'],
              [key: 'action', value: '$.action'],
              [key: 'merge_commit', value: '$.pull_request.merge_commit_sha'],
              [key: 'branch', value: '$.workflow_run.head_branch'],
              [key: 'repo', value: '$.repository.name'],
              [key: 'pull_request_title', value: '$.pull_request.title'],
              [key: 'result', value: '$.workflow_run.conclusion']
            ], 
            printContributedVariables: true, 
            printPostContent: true,
            regexpFilterExpression: 'completed\\smain\\ssuccess',
            regexpFilterText: '$action $branch $result',
            token: 'dingo-command'
        )
    }

    stages {
        stage('docker build') {
            when {
                anyOf { branch 'develop'; branch 'main' }
            }
            
            agent {
                node {
                    label "dingo_stack"
                }
            }
            steps {
                echo "build image harbor.zetyun.cn/dingostack/dingo-command:${IMAGE_TAG}"
                withCredentials([usernamePassword(credentialsId: 'harbor_credential', usernameVariable: 'HARBOR_USERNAME', passwordVariable: 'HARBOR_PASSWORD')]) {
                    sh 'podman login harbor.zetyun.cn -u $HARBOR_USERNAME -p $HARBOR_PASSWORD'
                }
                sh 'podman build -t harbor.zetyun.cn/dingostack/dingo-command:${IMAGE_TAG} -f docker/Dockerfile-local .'
                echo "Tagging dingo-command image as harbor.zetyun.cn/dingostack/dingo-command:${IMAGE_TAG}"

                sh 'podman push harbor.zetyun.cn/dingostack/dingo-command:${IMAGE_TAG}'

                echo 'podman push to second registry'
                sh 'podman tag harbor.zetyun.cn/dingostack/dingo-command:${IMAGE_TAG} 10.220.56.101:5000/dockerproxy.zetyun.cn/quay.nju.edu.cn/openstack.kolla/dingo-command:${IMAGE_TAG}'
                sh 'podman push 10.220.56.101:5000/dockerproxy.zetyun.cn/quay.nju.edu.cn/openstack.kolla/dingo-command:${IMAGE_TAG} --tls-verify=false'
            }
            
        }
        stage('Pull and Tag Images') {
            when {
                anyOf { branch 'develop'; branch 'main' }
            }
            
            agent {
                node {
                    label "dingo_stack"
                }
            }
            steps {
                echo "Pulling dingo-command image from harbor.zetyun.cn/dingostack/dingo-command:${IMAGE_TAG}"
                withCredentials([usernamePassword(credentialsId: 'harbor_credential', usernameVariable: 'HARBOR_USERNAME', passwordVariable: 'HARBOR_PASSWORD')]) {
                    sh 'podman login harbor.zetyun.cn -u $HARBOR_USERNAME -p $HARBOR_PASSWORD'
                }
                sh 'podman pull dockerproxy.zetyun.cn/docker.io/dingodatabase/dingo-command:latest'
                echo "Tagging dingo-command image as harbor.zetyun.cn/dingostack/dingo-command:${IMAGE_TAG}"
                sh 'podman tag dockerproxy.zetyun.cn/docker.io/dingodatabase/dingo-command:latest harbor.zetyun.cn/dingostack/dingo-command:${IMAGE_TAG}'
                sh 'podman push harbor.zetyun.cn/dingostack/dingo-command:${IMAGE_TAG}'

            }
            
        }
        stage('Deploy to test'){
            when {
                branch 'main'
            }
            parallel {
               
                stage('pull image') {
                    agent {
                        node {
                            label "dingo_stack"
                        }
                    }
            
                    steps {
                        echo "update kolla_ansible"
                        dir('/home/cicd/kolla-ansible') {
                             sh '''
                                git stash
                                git pull origin dingoStack
                                git stash pop || true
                                # 检查冲突
                                if git diff --name-only --diff-filter=U | grep .; then
                                    echo "出现冲突，请手动解决！"
                                    exit 1
                                fi
                            '''
                        }
                        echo "pull dingo-command images to test"
                        dir('/home/cicd/kolla-ansible/tools') {
                            sh 'ansible-playbook  -e @/home/cicd/envs/test-regionone/globals.yml -e @/home/cicd/envs/test-regionone/passwords.yml  --tags dingo-command -e openstack_tag=${IMAGE_TAG} -e kolla_action=pull ../ansible/site.yml  --inventory /home/cicd/envs/test-regionone/multinode -e CONFIG_DIR=/home/cicd/envs/test-regionone -e docker_namespace=openstack -e docker_registry=harbor.zetyun.cn'
                            echo 'deploy images to develop '
                            sh 'ansible-playbook  -e @/home/cicd/envs/test-regionone/globals.yml -e @/home/cicd/envs/test-regionone/passwords.yml  --tags dingo-command -e openstack_tag=${IMAGE_TAG} -e kolla_action=upgrade ../ansible/site.yml  --inventory /home/cicd/envs/test-regionone/multinode -e CONFIG_DIR=/home/cicd/envs/test-regionone -e docker_namespace=openstack -e docker_registry=harbor.zetyun.cn'
                        }
                    }
                }
                stage('pull image on second node') {
                    agent {
                        node {
                            label "dingo_stack"  // 请替换为实际的第二个节点标签
                        }
                    }

                    steps {
                        dir('/home/cicd/kolla-ansible') {
                             sh '''
                                git stash
                                git pull origin dingoStack
                                git stash pop || true
                                # 检查冲突
                                if git diff --name-only --diff-filter=U | grep .; then
                                    echo "出现冲突，请手动解决！"
                                    exit 1
                                fi
                            '''
                        }
                        echo "pull dingo-command images to test on second node"
                        dir('/home/cicd/kolla-ansible/tools') {
                            sh 'ansible-playbook -e @/home/cicd/envs/test-regiontwo/globals.yml -e @/home/cicd/envs/test-regiontwo/passwords.yml --tags dingo-command -e openstack_tag=${IMAGE_TAG} -e CONFIG_DIR=/home/cicd/envs/test-regiontwo -e kolla_action=pull ../ansible/site.yml  --inventory /home/cicd/envs/test-regiontwo/multinode -e docker_namespace=openstack -e docker_registry=harbor.zetyun.cn'
                            echo 'deploy images to develop on second node'
                            sh 'ansible-playbook -e @/home/cicd/envs/test-regiontwo/globals.yml -e @/home/cicd/envs/test-regiontwo/passwords.yml --tags dingo-command -e openstack_tag=${IMAGE_TAG} -e CONFIG_DIR=/home/cicd/envs/test-regiontwo -e kolla_action=upgrade ../ansible/site.yml  --inventory /home/cicd/envs/test-regiontwo/multinode -e docker_namespace=openstack -e docker_registry=harbor.zetyun.cn'
                        }
                    }
                }
            }
        }
        stage('deploy dingoOps to dev'){
            when {
                anyOf { branch 'develop'; branch 'stable/2023.2' }
            }

            parallel {
              
                stage('pull cinder') {
                    agent {
                        node {
                            label "dingo_stack"
                        }
                    }
                    steps {
                        echo "pull cinder images to dev"
                        sh 'kolla-ansible -i /root/multinode pull --tag cinder -e openstack_tag=${branch}'
                        echo 'deploy images to develop '
                        sh 'kolla-ansible -i /root/multinode upgrade --tag cinder -e openstack_tag=${branch}'
                    }
                }
            }
        }
    }
}
