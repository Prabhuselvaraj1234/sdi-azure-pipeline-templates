import argparse
import os.path
import re
import os
import shutil
import xml.etree.ElementTree as xml
import zipfile

TAB_SIZE = 2
POM_NS = 'http://maven.apache.org/POM/4.0.0'
NAMESPACES = {
  'pom': POM_NS
}

def yaml_to_dict(input_file, prefix = ''):
  if not os.path.isfile(input_file):
    raise ValueError(input_file + ' is not a valid file. Make sure it exists.')
  with open(input_file) as file_handle:
      lines = file_handle.readlines()
  prop_key_parts = []
  prop_dictionary = {}
  for line in lines:
    ignore = re.search(r'^\s*#', line)
    array_line = re.search(r'^\s*-\s', line) is not None
    if not array_line:
      array_index = -1
    if ignore or not line.strip() or not ':' in line and not array_line:
      continue

    tabs = re.findall(r'(' + (TAB_SIZE * '\s') + ')', line.split(':')[0])

    index = len(tabs) if tabs else 0

    key_part = re.search(r'.+(?=:\s)', line)
    if index == 0:
      prop_key_parts = []
      prop_key_parts.append(key_part.group().strip())
    else:
      if array_line:
        array_index += 1
      else:
        key_part = key_part.group(0).strip()
        while array_index < 0 and prop_key_parts and index < len(prop_key_parts):
          prop_key_parts.pop()
        if array_index < 0:
          prop_key_parts.append(key_part)

    if array_index < 0:
      value_part = re.search(r'(?<=:)\s*(["\'])(?P<value1>.+)\1|(?<=:)\s*(?P<value2>.+)', line)
    else:
      value_part = re.search(r'(?<=-\s)\s*(["\'])(?P<value1>.+)\1|(?<=-\s)\s*(?P<value2>.+)', line)

    if value_part:
      value_text = value_part.group('value1').strip() if value_part.group('value1') else value_part.group('value2').strip()
    else:
      value_text = None

    if value_text:
      key_text = prefix + '.'.join(prop_key_parts)
      prop_dictionary[key_text] = value_text
  return prop_dictionary

def prepare_artifact_metadata(pom, build_number):
    xml.register_namespace('', POM_NS) 
    pom_document = xml.parse(pom)
    artifact_id = pom_document.find('./pom:artifactId', NAMESPACES).text
    pom_version = pom_document.find('./pom:version', NAMESPACES).text
    parts = pom_version.split('.')
    release = {}
    release['artifactId'] = artifact_id
    release['majorVersion'] = parts[0]
    release['minorVersion'] = parts[1]
    release['patchVersion'] = parts[2]
    release['finalReleaseVersion'] = pom_version
    release['preReleaseVersion'] = pom_version + '-pre+' + str(build_number)
    for key, value in release.items():
      print (f'##vso[task.setvariable variable=release.{key}]{value}')
    return release

def prepare_final_pom(pom, final_pom, final_version = None):
  xml.register_namespace('', POM_NS) 
  pom_document = xml.parse(pom)

  if final_version:
    pom_document.find('./pom:version', NAMESPACES).text = final_version

  cloudhub_properties_element = pom_document.find('.//pom:cloudHubDeployment/pom:properties', NAMESPACES)

  property_element = xml.SubElement(cloudhub_properties_element, f'{{{POM_NS}}}anypoint.platform.client_id')
  property_element.text = '${anypointPlatformClientId}'

  property_element = xml.SubElement(cloudhub_properties_element, f'{{{POM_NS}}}anypoint.platform.client_secret')
  property_element.text = '${anypointPlatformClientSecret}'

  property_element = xml.SubElement(cloudhub_properties_element, f'{{{POM_NS}}}mule.env')
  property_element.text = '${muleConfigEnvironment}'

  property_element = xml.SubElement(cloudhub_properties_element, f'{{{POM_NS}}}mule.enc.key')
  property_element.text = '${anypointSecurePropertyKey}'

  pom_document.write(final_pom, xml_declaration = True, encoding = 'utf-8', method = 'xml')

def prepare_deployment_properties(application_binary, env_config_yaml, environment_name):
  target_dir = os.path.dirname(application_binary)
  binary_name = os.path.basename(application_binary)
  target_binary = f'{target_dir}/{environment_name}-{binary_name}'
  shutil.copy2(application_binary, target_binary)
  with zipfile.ZipFile(target_binary, 'a') as application_binary_handle:
    target_yaml_path = os.path.basename(env_config_yaml)
    application_binary_handle.write(env_config_yaml, target_yaml_path)

def main():
  parser = argparse.ArgumentParser()
  parser.add_argument(
    "--action",
    choices = ['prepare-artifact-metadata', 'prepare-final-pom', 'prepare-deployment-properties'],
    help = "The expected action to perform")

  parser.add_argument(
    "--source-root",
    dest = "source_root",
    help = "The root location of the application source code")

  parser.add_argument(
    "--config-root",
    dest = "config_root",
    help = "The root location of the application configuration")

  parser.add_argument(
    "--environment",
    help = "The current environment config name to be used for this execution")

  parser.add_argument(
    "--build-number",
    dest = "build_number",
    help = "The build number to be used in case of a pre-release build")

  parser.add_argument(
    "--artifact-id",
    dest = "artifact_id",
    help = "The artifact id of the application")

  parser.add_argument(
    "--final-version",
    dest = "final_version",
    help = "The final version number to use for the artifact")

  args = parser.parse_args()

  print(f'Action: {args.action}')
  print(f'Source Root: {args.source_root}')
  print(f'Config Root: {args.config_root}')
  print(f'Environment Config: {args.environment}')
  print(f'Build Number: {args.build_number}')
  print(f'Artifact ID: {args.artifact_id}')
  print(f'Final Version: {args.final_version}')

  if args.action == 'prepare-artifact-metadata':
    pom_location = args.source_root + '/pom.xml'
    prepare_artifact_metadata(pom_location, args.build_number)
  else:
    if args.action == 'prepare-final-pom':
      pom_location = args.source_root + '/pom.xml'
      final_pom_location = args.source_root + '/final-pom.xml'
      prepare_final_pom(pom_location, final_pom_location, args.final_version)
    elif args.action == 'prepare-deployment-properties':
      env_config_yaml = args.config_root + f'/app-config/{args.artifact_id}/{args.environment}.yaml'
      application_binary = f'{args.source_root}/target/{args.artifact_id}-{args.final_version}-mule-application.jar'
      prepare_deployment_properties(application_binary, env_config_yaml, args.environment)

if __name__ == "__main__":
  main()