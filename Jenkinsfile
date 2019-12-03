def versionValue
def exportlocation
def workspacelocation
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
		//*1c
        V83PATH = "C:\\Program Files\\1cv8\\8.3.14.1630\\bin\\1cv8.exe"
		//*Runner
        RUNNER_IBCONNECTION = "/F./InfoBase1"
        RUNNER_LANGUAGE = "ru"
        RUNNER_LOCALE = "ru_RU"
        RUNNER_v8version = "8.3.14.1630"
	    RUNNER_DBUSER = ""
		//*EDT
		RING_OPTS="-Dfile.encoding=UTF-8 -Dosgi.nl=ru"
		WP="F:\\Users\\FTimokhov\\workspace"
		PRJ="FormEditor"
		XML="${workspacelocation}\\xml_export"
		//*Temp base
        workspacelocation = "N:\\jenkins_workspace\\workspace\\FTimokhov_FormModificator"		
		DumpLocation = "${workspacelocation}\\dumpcfg"
		DumpLogLocation = "${workspacelocation}\\dumpcfg.log"
		WorkspacePath = "${workspacelocation}"
		FOLDERIB = "${workspacelocation}\\InfoBase1"		
		//*Release
		ReleaseFolder = "F:\\Users\\FTimokhov\\Release"
    }
    stages {
        stage('XML Export') {
            steps {
                timeout(120) {
                    bat """@chcp 65001
					ring -x edt@1.15.0:x86_64 workspace export --workspace-location \"${WP}\" --project-name \"${PRJ}\" --configuration-files \"${XML}\"
                    """
                }
            }
        }
        stage('Make db') {
            steps {
                timeout(120) {
                    bat """@chcp 65001
					runner init-dev --src ${XML} --nocacheuse
                    """
                }
            }
        }	
        stage('Get version') {
            steps {
 					timestamps {				
						//*Получение версии из базы
                        bat """@chcp 65001  
						call \"${V83PATH}\" DESIGNER /F\"${FOLDERIB}\" /N \"\" /P \"\" /DumpResult ${WorkspacePath} /Out ${DumpLogLocation} /DumpConfigToFiles \"${DumpLocation}\" -listFile \"${WorkspacePath}\\filelist.txt\"
                        copy %DumpLocation%\\Configuration.xml ${WorkspacePath}\\Configuration.xml
						rmdir /S /Q ${DumpLocation} 
						"""
					}				
					script {
						versionText = readFile encoding: 'UTF-8', file: './Configuration.xml'
						versionValue = (versionText =~ /<Version>(.*)<\/Version>/)[0][1]
						exportlocation  = versionValue+"\\"
					}			  
			    	 bat """@chcp 65001  
				     Echo Ver: ${versionValue} 
				     """
            }
        }	
		stage ('Make release') {
			steps {
					timestamps {
					bat """@chcp 65001  
					\"${V83PATH}\" DESIGNER /F\"${FOLDERIB}\" /N \"\" /P \"\" /CreateDistributionFiles -cffile \"${ReleaseFolder}\\${exportlocation}1cv8.cf\" /Out log.log           
					"""
					}						  
			} 
		}	
		stage ('Clean workspace') {
			steps {
					timestamps {
					bat """@chcp 65001  
					rmdir /S /Q ${FOLDERIB} 
					rmdir /S /Q ${XML} 					
					"""
					}						  
			} 
		}		
        stage('test') {
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
