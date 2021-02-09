import ctypes
import difflib
import hashlib
import json
from json.decoder import JSONDecodeError
import os
import pickle
import random
import re
import shutil
import sys
import tempfile
import webbrowser
import zipfile
from datetime import datetime
from signal import SIGTERM
from subprocess import PIPE, CalledProcessError, Popen, call, check_call
from timeit import default_timer as timer
from Classes.JsonCompress import JSONCompress


import click
import cursor
import keyboard
import pyperclip as clipboard
import requests
from colorama import Back, Fore, Style
from googlesearch import search
from halo import Halo
from switch import Switch

import info
import registry
from Classes.Metadata import Metadata
from Classes.Packet import Packet
from Classes.PathManager import PathManager
from headers import *
from extension import *
from limit import *
from logger import *
from registry import *
from viruscheck import virus_check

index = 0
final_value = None
path = ''

appdata_dir = PathManager.get_appdata_directory()


def get_recent_logs() -> list:
    """
    Reads all recent logs from %appdata%\electric-log.log
    Used to create the log attachment for the support ticket.

    Returns:
        list: Recent logs in the form of a list
    """    
    with open(Rf'{appdata_dir}\electric-log.log', 'r') as file:
        data = file.read()
    return data.splitlines()


def generate_report(name: str, version: str) -> str:
    """
    Generate support ticket info including version and name of software.

    Args:
        name (str): Name of the package that failed to install / uninstall.
        version (str): Version of the package that failed to install / uninstall.

    Returns:
        str: Support ticket to echo to output
    """    
    return f'''
{{
Name {Fore.MAGENTA}=>{Fore.RESET} {Fore.YELLOW}{name}{Fore.RESET}
{Fore.LIGHTRED_EX}Version {Fore.MAGENTA}=>{Fore.RESET} {Fore.BLUE}{version}{Fore.GREEN}
{Fore.LIGHTBLUE_EX}Logfile {Fore.MAGENTA}=>{Fore.RESET} {Fore.CYAN}<--attachment-->{Fore.GREEN}
}}{Fore.RESET}
    '''


def is_admin() -> bool:
    """
    Checks if electric is running as administrator.

    Returns:
        bool: If electric is run as administrator
    """    
    try:
        is_admin = (os.getuid() == 0)
    except AttributeError:
        is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0
    return is_admin


def generate_dict(path: str, package_name: str) -> dict:
    """
    Generates dictionary to dump to the downloadcache.pickle

    Args:
        path (str): Path to the installer
        package_name (str): Name of the package being installed

    Returns:
        dict: The data to dump to the downloadcache as a dictionary
    """    
    return {
        'directory': path,
        'package_name': package_name,
        'size': os.stat(path).st_size,
    }


def dump_pickle(data: dict, filename: str):
    """
    Dump a dictionary to a pickle file in the temp download directory for resuming or using existing downloads

    Args:
        data (dict): Data to dump to the pickle file
        filename (str): Name of the file to dump the data to in the temp directory
    """    
    with open(Rf'{tempfile.gettempdir()}\electric\{filename}.pickle', 'wb') as f:
        pickle.dump(data, f)


def retrieve_data(filename: str) -> dict:
    """
    Retrieve or read data from a pickle file in the temp download directory

    Args:
        filename (str): Name of the pickle file to read from in the temp directory

    Returns:
        dict: Data inside the pickle file in the form of a dictionary
    """
    if os.path.isfile(Rf'{tempfile.gettempdir()}\electric\{filename}.pickle'):
        with open(Rf'{tempfile.gettempdir()}\electric\{filename}.pickle', 'rb') as f:
            final = pickle.loads(f.read())
            return final


def check_existing_download(package_name: str, download_type) -> bool:
    data = retrieve_data('downloadcache')
    if data:
        if data['package_name'] == package_name:
            try:
                filesize = os.stat(data['directory'] + download_type).st_size
            except FileNotFoundError:

                if download_type not in data['directory']:
                    os.rename(data['directory'], data['directory'] + download_type)
                try:
                    filesize = os.stat(data['directory']).st_size
                except FileNotFoundError:
                    filesize = os.stat(data['directory'] + download_type).st_size
            if filesize < data['size']:
                # Corrupt Installation
                return False
            return data['directory']
    return False


def get_chunk_size(total_size: str) -> int:
    """
    Get the download iter chunk size, could increase speeds based on file size

    Args:
        total_size (str): Size of the download

    Returns:
        int: Chunk iter size for downloading the file
    """    
    size = int(total_size)
    size = size / 1000000
    if size < 7:
        return 4096
    else:
        return 7096


def check_resume_download(package_name: str, download_url: str, metadata: Metadata) -> tuple:
    """
    Check if an existing download can be resumed instead of redownloading from the start

    Args:
        package_name (str): Name of the package being installed
        download_url (str): Url for the file being downloaded
        metadata (Metadata): Metadata for the installation

    Returns:
        tuple: Size and directory of the file to resume downloading
    """
    data = retrieve_data('unfinishedcache')
    try:
        if os.path.isfile(data['path']) and package_name == data['name'] and data['url'] == download_url:
            write(f'Resuming Existing Download At => {tempfile.gettempdir()}', 'blue', metadata)
            return os.stat(data['path']).st_size, data['path']
        else:
            return (None, None)
    except:
        return (None, None)
    

def send_req_bundle() -> dict:
    """
    Send a network request to the API for the bundles to be installed

    Returns:
        dict: The json response from the network request
    """    
    REQA = 'https://electric-package-manager.herokuapp.com/bundles/windows'
    time = 0.0
    response = requests.get(REQA, timeout=15)
    res = response.json()
    time = response.elapsed.total_seconds()
    return res, time


def get_init_char(start, metadata) -> str:
    if start:
        try:
            start_char = Fore.RESET + metadata.settings.raw_dictionary['customProgressBar']['start_character']
        except:
            return ''
        return start_char if start_char else ''
    else:
        try:
            end_char = Fore.RESET + \
                metadata.settings.raw_dictionary['customProgressBar']['end_character']
        except:
            return ''
        return end_char if end_char else ''


def get_character_color(fill, metadata):
    if fill:
        try:
            fill_char_color = metadata.settings.raw_dictionary['customProgressBar']['fill_character_color']
        except:
            return 'Fore.RESET'
        return f'Fore.{fill_char_color.upper()}'if fill_char_color else 'Fore.RESET'
    else:
        try:
            unfill_char_color = metadata.settings.raw_dictionary['customProgressBar']['unfill_character_color']
        except:
            return 'Fore.RESET'
        return f'Fore.{unfill_char_color.upper()}' if unfill_char_color else 'Fore.RESET'


def download_supercache(url: str) -> str:
    """
    Download supercache into %APPDATA%\electric\SuperCache\supercache.txt 

    Args:
        url (str): Url to download the supercache.txt from

    Returns:
        str: %APPDATA%\electric\SuperCache\supercache.txt
    """    
    cursor.hide()
    response = requests.get(url, stream=True)
    total_length = response.headers.get('content-length')
    chunk_size = 5696

    with open(fR'{PathManager.get_appdata_directory()}\SuperCache\supercache.txt', 'wb') as f:
        if total_length is None:
            f.write(response.content)
        else:
            dl = 0
            full_length = int(total_length)
            for data in response.iter_content(chunk_size=chunk_size):
                dl += len(data)
                f.write(data)

                complete = int(25 * dl / full_length)
                fill_c =  Fore.GREEN + '=' * complete
                unfill_c = Fore.LIGHTBLACK_EX + '-' * (25 - complete)
                sys.stdout.write(
                    f'\r{fill_c}{unfill_c} {Fore.RESET + Style.DIM} {round(dl / 10000, 1)} / {round(full_length / 10000, 1)} KB {Fore.RESET}')
                sys.stdout.flush()

    return fR'{PathManager.get_appdata_directory()}\SuperCache\supercache.txt'


def download(url: str, package_name: str, metadata: Metadata, download_type: str):
    """
    Official electric downloader, uses requests to download files from a url.
    Can resume from existing downloads or detect already existing installers in the case of a reinstall.

    Args:
        url (str): The url to download the file / installer from
        package_name (str): The name of the package being installed
        metadata (Metadata): Metadata for the installation
        download_type (str): The extension to the file being downloaded

    Returns:
        str: Path to the downloaded installer
    """    
    cursor.hide()
    path = check_existing_download(package_name, download_type)
    if not os.path.isdir(Rf'{tempfile.gettempdir()}\electric'):
        os.mkdir(Rf'{tempfile.gettempdir()}\electric')

    if isinstance(path, bool):
        path = Rf'{tempfile.gettempdir()}\electric\Setup{download_type}'
    else:
        write(f'Found Existing Download At => {tempfile.gettempdir()}', 'blue', metadata)
        return path

    while os.path.isfile(path):
        path = Rf'{tempfile.gettempdir()}\electric\Setup{random.randint(200, 100000)}'

    size, newpath = check_resume_download(package_name, url, metadata)

    if not size:
        dump_pickle({'path': path, 'url': url, 'name': package_name, 'download-type': download_type}, 'unfinishedcache')

    with open(newpath if newpath else path, 'wb' if not size else 'ab') as f:
        if size:
            response = requests.get(url, stream=True, headers={'Range': 'bytes=%d-' % size})
        else:
            response = requests.get(url, stream=True)
        total_length = response.headers.get('content-length')
        chunk_size = get_chunk_size(total_length)

        progress_type = metadata.settings.progress_bar_type

        if total_length is None:
            f.write(response.content)
        else:
            dl = 0
            full_length = int(total_length)
            for data in response.iter_content(chunk_size=chunk_size):
                dl += len(data)
                f.write(data)

                if metadata.no_progress == True or metadata.settings.show_progress_bar == False:
                    sys.stdout.write(
                        f'\r{round(dl / 1000000, 1)} / {round(full_length / 1000000, 1)} MB')
                    sys.stdout.flush()


                elif not metadata.no_progress and not metadata.silent:
                    complete = int(25 * dl / full_length)
                    if progress_type == 'custom' or metadata.settings.use_custom_progress_bar:
                        fill_c = eval(get_character_color(True, metadata))  + metadata.settings.raw_dictionary['customProgressBar']['fill_character'] * complete
                        unfill_c = eval(get_character_color(False, metadata)) + metadata.settings.raw_dictionary['customProgressBar']['unfill_character']  * (25 - complete)
                    elif progress_type == 'accented':
                        fill_c =  Fore.LIGHTBLACK_EX + Style.DIM + '█' * complete
                        unfill_c = Fore.BLACK + '█' * (25 - complete)
                    elif progress_type == 'zippy':
                        fill_c =  Fore.GREEN + '=' * complete
                        unfill_c = Fore.LIGHTBLACK_EX + '-' * (25 - complete)
                    elif progress_type not in ['custom', 'accented', 'zippy'] and metadata.settings.use_custom_progress_bar == False or progress_type == 'default':
                        fill_c =  Fore.LIGHTBLACK_EX + Style.DIM + '█' * complete
                        unfill_c = Fore.BLACK + '█' * (25 - complete)

                    if metadata.settings.electrify_progress_bar == True and not metadata.settings.use_custom_progress_bar:
                        sys.stdout.write(
                        f'\r{fill_c}{unfill_c} {Fore.RESET + Style.DIM} ⚡ {round(dl / 1000000, 1)} / {round(full_length / 1000000, 1)} MB {Fore.RESET}⚡')
                    else:
                        sys.stdout.write(
                            f'\r{get_init_char(True, metadata)}{fill_c}{unfill_c}{get_init_char(False, metadata)} {Fore.RESET + Style.DIM} {round(dl / 1000000, 1)} / {round(full_length / 1000000, 1)} MB {Fore.RESET}')
                    sys.stdout.flush()

    os.remove(Rf"{tempfile.gettempdir()}\electric\unfinishedcache.pickle")
    dump_pickle(generate_dict(newpath if newpath else path, package_name), 'downloadcache')
    
    if not newpath:
        return path
    else:
        return newpath


def get_error_cause(error: str, install_exit_codes: list, uninstall_exit_codes: list, method: str, metadata: Metadata, packet: Packet) -> str:
    """
    Troubleshoots errors when a CalledProcessError, OSError or FileNotFoundError is caught through subprocess.run in run_cmd. 

    IMPORTANT: `method` here refers to installation or uninstallation
    Args:
        error (str): Error written to stderr to troubleshoot
        install_exit_codes (list): Valid install exit codes which are valid to be ignored
        uninstall_exit_codes (list):  Valid uninstall exit codes which are valid to be ignored
        method (str): Installation or Uninstallation method
        metadata (Metadata): Metadata for the method
        packet (Packet): Packet used for the method


    Returns:
        str: Error message to log
    """
    log_info(f'{error} ==> {method}', metadata.logfile)
    valid_i_exit_codes = valid_install_exit_codes
    valid_u_exit_codes = valid_uninstall_exit_codes

    if install_exit_codes:
        for i in install_exit_codes:
            valid_i_exit_codes.append(i)

    if uninstall_exit_codes:
        for i in uninstall_exit_codes:
            valid_u_exit_codes.append(i)

    if method == 'installation':
        for code in valid_i_exit_codes:
            if f'exit status {code}' in error:
                return ['no-error']

    if method == 'uninstallation':
        for code in valid_u_exit_codes:
            if f'exit status {code}' in error:
                return ['no-error']

    if 'exit status 1603' in error:
        if method == 'installation' and not is_admin():
            flags = ''
            for flag in get_install_flags(packet.directory, metadata):
                flags += f' {flag}'
            click.echo(click.style(f'The {packet.display_name} Installer Has Requested Administrator Permissions, Using Auto-Elevate', 'yellow'))
            os.system(rf'"{PathManager.get_current_directory()}\scripts\elevate-installation.cmd" {packet.json_name} {flags}')
            sys.exit()
        if method == 'uninstallation' and not is_admin():
            flags = ''
            for flag in get_install_flags(packet.directory, metadata):
                flags += f' {flag}'
            flags = flags.replace(' --sync', '')
            flags = flags.replace(' --install-dir', '')
            flags = flags.replace(' --reduce', '')
            click.echo(click.style(f'The {packet.display_name} Uninstaller Has Requested Administrator Permissions, Using Auto-Elevate', 'yellow'))
            os.system(rf'"{PathManager.get_current_directory()}\scripts\elevate-uninstallation.cmd" {packet.json_name} {flags}')
            click.echo(click.style('\nAdministrator Elevation Required Or Fatal Installer Error. Exit Code [1603]', fg='red'))
            sys.exit()
        click.echo(click.style('\nFatal Installer Error. Exit Code [1603]', fg='red'))
        return get_error_message('1603', 'installation', packet.display_name, packet.version)

    if 'exit status 1639' in error:
        click.echo(click.style(f'\nElectric Installer Passed In Invalid Parameters For Installation. Exit Code [0002]', fg='red'))
        return get_error_message('0002', 'installation', packet.display_name, packet.version)

    if 'exit status 1' in error:
        click.echo(click.style(f'\nUnknown Error. Exited With Code [0000]', fg='red'))
        handle_unknown_error(error)
        return get_error_message('0000', 'installation', packet.display_name, packet.version)

    if '[WinError 740]' in error and 'elevation' in error:
        # Process Needs Elevation To Execute
        if method == 'installation':
            flags = ''
            for flag in get_install_flags(packet.directory, metadata):
                flags += f' {flag}'
            
            click.echo(click.style(f'The {packet.display_name} Installater Has Requested Administrator Permissions, Using Auto-Elevate', 'yellow'))
            os.system(rf'"{PathManager.get_current_directory()}\scripts\elevate-installation.cmd" {packet.json_name} {flags}')
            sys.exit()
        if method == 'uninstallation':
            flags = ''
            for flag in get_install_flags(packet.directory, metadata):
                flags += f' {flag}'
            flags = flags.replace(' --sync', '')
            flags = flags.replace(' --install-dir', '')
            flags = flags.replace(' --reduce', '')
            click.echo(click.style(f'The {packet.display_name} Uninstaller Has Requested Administrator Permissions, Using Auto-Elevate', 'yellow'))
            os.system(rf'"{PathManager.get_current_directory()}\scripts\elevate-uninstallation.cmd" {packet.json_name} {flags}')
            sys.exit()
        

    if 'exit status 2' in error or 'exit status 1' in error:
        click.echo(click.style(f'\nAdministrative Privileges Declined. Exit Code [0101]', fg='red'))
        return get_error_message('0101', 'installation', packet.display_name, packet.version)

    if 'exit status 4' in error:
        # Fatal Error During Installation
        click.echo(click.style(f'\nFatal Error. Exit Code [1111]', fg='red'))
        return get_error_message('1111', 'installation', packet.display_name, packet.version)

    if '[WinError 87]' in error and 'incorrect' in error:
        click.echo(click.style(f'\nElectric Installer Passed In Invalid Parameters For Installation. Exit Code [0002]', fg='red'))
        return get_error_message('0002', 'installation', packet.display_name, packet.version)

    if 'exit status 3010' or 'exit status 2359301' in error:
        # Installer Requesting Reboot
        return get_error_message('1010', 'installation', packet.display_name, packet.version)

    else:
        click.echo(click.style(f'\nUnknown Error. Exited With Code [0000]', fg='red'))
        handle_unknown_error(error)
        return get_error_message('0000', 'installation', packet.display_name, packet.version)


def get_file_type(command: str) -> str:
    """
    Used to understand if a command run uses a .msi or a .exe installer / uninstaller

    Args:
        command (str): The command to infer the installer type from

    Returns:
        str: The filetype of the installer infered from the command
    """    
    if 'msiexec.exe' in command.lower():
        return '.msi'
    return '.exe'


def run_cmd(command: str, metadata: Metadata, method: str, halo: Halo, packet: Packet) -> bool:
    command = command.replace('\"\"', '\"').replace('  ', ' ')
    log_info(f'Running command: {command}', metadata.logfile)
    write_debug(f'{command}', metadata)
    try:
        exit_code = check_call(command, stdin=PIPE, stdout=PIPE, stderr=PIPE)
        return False if exit_code == 0 else True
    except (CalledProcessError, OSError, FileNotFoundError) as err:
        if halo:
            halo.stop()
        keyboard.add_hotkey(
        'ctrl+c', lambda: os._exit(0))
        disp_error_msg(get_error_cause(str(err), packet.install_exit_codes, packet.uninstall_exit_codes, method, metadata, packet), metadata)


def install_package(path, packet: Packet, metadata: Metadata, halo: Halo) -> str:
    download_type = packet.win64_type
    custom_install_switch = packet.custom_location
    directory = packet.directory
    package_name = packet.json_name
    switches = packet.install_switches
    no_cache = metadata.no_cache
    sync = metadata.sync

    if download_type == '.exe':
        if '.exe' not in path:
            if not os.path.isfile(path + '.exe'):
                os.rename(path, f'{path}.exe')
            path = path + '.exe'
        command = path + ' '

        if custom_install_switch:
            if directory and directory != '':
                if '/D=' in custom_install_switch:
                    idx = 0
                    for switch in switches:
                        if idx == 0:
                            command = command + switch
                            continue
                        command = command + ' ' + switch
                        idx += 1

                    command += ' ' + custom_install_switch + f'{directory}'
                else:
                    for switch in switches:
                        command += ' ' + switch

                    command += ' ' + custom_install_switch + f'"{directory}"'
                if directory == '':
                    click.echo(click.style(
                        f'Installing {package_name} To Default Location, Custom Installation Directory Not Supported By This Installer!', fg='yellow'))

        if not directory:
            for switch in switches:
                command = command + ' ' + switch

        run_test = run_cmd(command, metadata, 'installation', halo, packet)
        packet.run_test = run_test

    elif download_type == '.msi':
        command = 'msiexec.exe /i ' + path + ' '
        for switch in switches:
            command = command + ' ' + switch

        if not is_admin():
            flags = ''
            for flag in get_install_flags(packet.directory, metadata):
                flags += f' {flag}'
            click.echo(click.style(f'The {packet.display_name} Uninstaller Has Requested Administrator Permissions, Using Auto-Elevate', 'yellow'))
            os.system(rf'"{PathManager.get_current_directory()}\scripts\elevate-installation.cmd" {packet.json_name} {flags}')
            sys.exit()
        run_test = run_cmd(command, metadata, 'installation', halo, packet)
        packet.run_test = run_test


def get_configuration_data(username: str, description: str, uses_editor: bool, include_editor: bool, editor: str, include_python: bool, include_node: bool):
    base_configuration = [
        '[ Info ]\n',
        '# Go To https://www.electric.sh/electric-configuration-documentation/ For More Information\n',
        f'Publisher => \"{username}\"\n',
        f'Description => \"{description}\"\n'
    ]

    required_packages = []

    if uses_editor and include_editor and editor:
        base_configuration.append('\n[ Editor-Configuration ]\n')
        if editor == 'Visual Studio Code':
            base_configuration.append(f'Editor => \"{editor}\"\n\n[ Editor-Extensions ]\n<vscode:name>\n')
            required_packages.append('visual-studio-code')
        if editor == 'Atom':
            base_configuration.append(
                f'Editor => \"{editor}\"\n\n[ Editor-Extensions ]\n<atom:name>\n')
            required_packages.append('atom')

    if include_python:
        base_configuration.append('\n[ Pip-Packages ]\n<pip:name>\n')
        required_packages.append('python')

    if include_node:
        base_configuration.append('\n[ Node-Packages ]\n<npm:name>\n')
        required_packages.append('nodejs')

    requirements = str(required_packages).replace('[', '').replace(']', '').replace(',', '\n').replace('\'', '').replace('\n ', '\n')
    base_configuration.insert(4, f'\n[ Packages ]\n{requirements}\n')
    return base_configuration

# IMPORTANT: FOR FUTURE USE
def get_hash_algorithm(checksum: str):
    # A function to detect the hash algorithm used in checksum
    hashes = {32: 'md5', 40: 'sha1', 64: 'sha256', 128: 'sha512'}
    return hashes[len(checksum)] if len(checksum) in hashes else None


def get_checksum(bytecode: bytes, hash_algorithm: str):
    # A function to get the checksum from bytecode
    hash_type = getattr(hashlib, hash_algorithm, None)

    if hash_type:
        return hash_type(bytecode).hexdigest()

    return None


def send_req_package(package_name: str) -> dict:
    REQA = 'https://electric-package-manager.herokuapp.com/packages/windows/'
    response = requests.get(REQA + package_name, timeout=15)
    time = response.elapsed.total_seconds()
    try:
        res = json.loads(response.text)
    except JSONDecodeError:
        click.echo(click.style(f'{package_name} not found!', 'red'))
        sys.exit()
    return res, time


def get_pid(exe_name):
    proc = Popen('tasklist', stdin=PIPE, stdout=PIPE, stderr=PIPE)
    output, _ = proc.communicate()
    output = output.decode('utf-8')
    lines = output.splitlines()
    for line in lines:
        if exe_name in line:
            return line.split()[1]


def find_approx_pid(exe_name, display_name) -> str:
    proc = Popen('tasklist /FI "Status eq RUNNING"', stdin=PIPE, stdout=PIPE, stderr=PIPE)
    output, _ = proc.communicate()
    output = output.decode('utf-8')
    lines = output.splitlines()

    cleaned_up_names = []
    for line in lines:
        try:
            cleaned_up_names.append(line.split()[0].replace('.exe', '').lower())
        except IndexError:
            continue

    matches = difflib.get_close_matches(display_name.lower(), cleaned_up_names, n=1, cutoff=0.65)

    if matches != []:
        for line in lines:
            if matches[0] in line.lower():
                return line.split()[1]

    return 1


def handle_exit(status: str, setup_name: str, metadata: Metadata):
    if status == 'Downloaded' or status == 'Installing' or status == 'Installed':
        exe_name = setup_name.split('\\')[-1]
        os.kill(int(get_pid(exe_name)), SIGTERM)

        print(Fore.RESET, '')
        write('SafetyHarness Successfully Created Clean Exit Gateway',
              'green', metadata)
        write('\nRapidExit Using Gateway From SafetyHarness Successfully Exited With Code 0',
              'light_blue', metadata)
        # print(Fore.RESET, '')
        sys.exit()

    if status == 'Got Download Path':
        print(Fore.RESET, '')
        write('\nRapidExit Successfully Exited With Code 0', 'green', metadata)
        # print(Fore.RESET, '')
        sys.exit()

    if status == 'Downloading':
        print(Fore.RESET, '')
        write('\n\nRapidExit Successfully Exited With Code 0', 'green', metadata)
        # print(Fore.RESET, '')
        sys.exit()

    else:
        print(Fore.RESET, '')
        write('RapidExit Successfully Exited With Code 0', 'green', metadata)
        # print(Fore.RESET, '')
        sys.exit()

def kill_running_proc(package_name: str, display_name: str, metadata: Metadata):
    parts = package_name.split('-')
    name = ' '.join([p.capitalize() for p in parts])
    pid = int(find_approx_pid(package_name, display_name))
    if pid == 1:
        return
    if pid and pid != 1:
        if metadata.yes:
            write(f'Terminating {name}.', 'green', metadata)
            os.kill(pid, SIGTERM)
            return
        if metadata.silent:
            os.kill(pid, SIGTERM)
            return
        terminate = click.confirm(
            f'Electric Detected {name} Running In The Background. Would You Like To Terminate It?')
        if terminate:
            write(f'Terminating {name}.', 'green', metadata)
            os.kill(pid, SIGTERM)
        else:
            write('Aborting Installation!', 'red', metadata)
            write_verbose(
                f'Aborting Installation Due To {name} Running In Background', metadata)
            write_debug(
                f'Aborting Installation Due To {name} Running In Background. Process Was Not Terminated.', metadata)
            os._exit(1)


def kill_proc(proc, metadata: Metadata):
    if proc is not None:
        proc.terminate()
        write('SafetyHarness Successfully Created Clean Exit Gateway',
              'green', metadata)
        write('\nRapidExit Using Gateway From SafetyHarness Successfully Exited With Code 0',
              'light_blue', metadata)
        os._exit(0)
    else:
        write('\nRapidExit Successfully Exited With Code 0',
              'green', metadata)
        os._exit(0)


def assert_cpu_compatible() -> int:
    cpu_count = os.cpu_count()
    print(cpu_count)


def find_existing_installation(package_name: str, display_name: str, test=True):
    key = registry.get_uninstall_key(package_name, display_name)
    installed_packages = [ f.replace('.json', '') for f in os.listdir(PathManager.get_appdata_directory() + r'\Current') ]
    if key:
        if not test:
            if package_name in installed_packages:
                return True
            return False
        return True
    return False


def get_install_flags(install_dir: str, metadata: Metadata):
    flags = []
    if metadata.verbose:
        flags.append('--verbose')
    if metadata.debug:
        flags.append('--debug')
    if metadata.no_color:
        flags.append('--no-color')
    if metadata.no_progress:
        flags.append('--no-progress')
    if metadata.yes:
        flags.append('--yes')
    if metadata.silent:
        flags.append('--silent')
    if metadata.logfile:
        flags.append('--logfile')
    if metadata.virus_check:
        flags.append('--virus-check')
    if metadata.reduce_package:
        flags.append('--reduce')
    if metadata.rate_limit != -1 and metadata.rate_limit:
        flags.append(f'--rate-limit={metadata.rate_limit}')
    if install_dir:
        flags.append(f'--install-dir={install_dir}')
    if metadata.sync:
        flags.append('--sync')
    if metadata.no_cache:
        flags.append('--no-cache')

    return flags


def refresh_environment_variables():
    proc = Popen('powershell -c "$env:Path = [System.Environment]::GetEnvironmentVariable(\'Path\',\'Machine\') + \';\' + [System.Environment]::GetEnvironmentVariable(\'Path\',\'User\')"'.split(), stdin=PIPE, stdout=PIPE, stderr=PIPE, shell=True)
    proc.communicate()


def check_virus(path: str, metadata: Metadata):
    detected = virus_check(path)
    if detected:
        for value in detected.items():
            if not metadata.silent and not metadata.no_color:
                click.echo(click.style(f'\n{value[0]} => {value[1]}', fg='yellow'))
            elif metadata.no_color and not metadata.silent:
                click.echo(click.style(f'\n{value[0]} => {value[1]}', fg='white'))
            else:
                continue_install = 'y'
        if not metadata.silent:
            continue_install = click.confirm('Would You Like To Continue?')
            if continue_install:
                pass
            else:
                handle_exit('Virus Check', '', metadata)
    else:
        click.echo(click.style('No Viruses Detected!', fg='green'))


def setup_supercache(call: bool = False):
    home = os.path.expanduser('~')
    if not os.path.isdir(f'{home}\\electric'):
        os.mkdir(f'{home}\\electric')
    supercache_dir = PathManager.get_appdata_directory() + R'\SuperCache'
    try:
        exist = len(os.listdir(supercache_dir)) != 0
    except FileNotFoundError:
        exist = False

    if call:
        shutil.rmtree(supercache_dir)
    
    
    if not os.path.isdir(supercache_dir) or not exist or call:
        with Halo('Setting Up SuperCache ', text_color='green') as h:
            if not os.path.isdir(supercache_dir):
                os.mkdir(supercache_dir)
            res = requests.get('https://electric-package-manager.herokuapp.com/setup/name-list', timeout=15)
            name_list = json.loads(res.text)
            with open(fR'{supercache_dir}\packages.json', 'w+') as f:
                f.write(json.dumps(name_list, indent=4))
            h.stop()
            loc = download_supercache('https://electric-package-manager.herokuapp.com/setup/supercache')
            with open(loc, 'rb') as f:
                data = eval(JSONCompress.load_compressed_file(f))
                keys = data.keys()
            with open('supercache.json', 'w+') as f:
                f.write(json.dumps(data, indent=4))
            h.stop()
            with Bar(f'{Fore.CYAN}Generating SuperCache{Fore.RESET}', max=len(keys), bar_prefix=' [ ', bar_suffix=' ] ', fill=f'{Fore.GREEN}={Fore.RESET}', empty_fill=f'{Fore.LIGHTBLACK_EX}-{Fore.RESET}') as b:
                for key in keys:
                    base_loc = loc.replace('\supercache.txt', '')
                    with open(base_loc + rf'\{key}' + '.json', 'w+') as f:
                        json.dump(data[key], f, indent=4)
                    time.sleep(0.0075)
                    b.next()
            os.remove(loc)
            click.echo(click.style('Successfully Generated SuperCache!', 'green'))
            cursor.hide()
            Popen('electric update all --local'.split(), shell=True)

def update_supercache(metadata: Metadata):
    if isfile(f'{tempfile.gettempdir()}\electric'):
        log_info(f'Removing all data in {tempfile.gettempdir()}\electric', metadata.logfile)
        shutil.rmtree(f'{tempfile.gettempdir()}\electric')
        log_info(f'Deleted all data in {tempfile.gettempdir()}\electric successfully.', metadata.logfile)

    setup_supercache(True)
    logpath = Rf'{appdata_dir}\superlog.txt'
    logfile = open(logpath, 'w+')
    now = datetime.now()
    log_info(f'Writing {str(now)} to {logpath}', metadata.logfile if metadata else None)
    logfile.write(str(now))
    logfile.close()
    log_info(f'Successfully wrote date and time to {logpath}', metadata.logfile if metadata else None)


def check_newer_version(package_name: str, packet: Packet) -> bool:
    install_dir = PathManager.get_appdata_directory() + r'\Current'
    with open(rf'{install_dir}\{package_name}.json', 'r') as f:
        data = json.load(f)
    installed_version = data['version']    
    if installed_version != packet.version:
        return True
    return False    

def check_newer_version_local(new_version) -> bool:
    current_version = int(info.__version__.replace('.', '').replace('a', '').replace('b', ''))
    new_version = int(new_version.replace('.', ''))
    if current_version < new_version:
        return True
    return False


def check_for_updates():
    res = requests.get('https://electric-package-manager.herokuapp.com/version/windows', timeout=10)
    js = res.json()
    version_dict = json.loads(js)

    if version_dict:
        new_version = version_dict['version']
        if check_newer_version_local(new_version):
            # Implement Version Check
            if click.confirm('A new update for electric is available, would you like to proceed with the update?'):
                click.echo(click.style('Updating Electric..', fg='green'))
                UPDATEA = 'https://electric-package-manager.herokuapp.com/update/windows'

                def is_admin():
                    try:
                        return ctypes.windll.shell32.IsUserAnAdmin()
                    except:
                        return False


                if is_admin():
                    with open(Rf'C:\Program Files (x86)\Electric\Update.7z', 'wb') as f:
                        response = requests.get(UPDATEA, stream=True)
                        total_length = response.headers.get('content-length')

                        if total_length is None:
                            f.write(response.content)
                        else:
                            dl = 0
                            full_length = int(total_length)

                            for data in response.iter_content(chunk_size=7096):
                                dl += len(data)
                                f.write(data)

                                complete = int(20 * dl / full_length)
                                fill_c, unfill_c = '#' * complete, ' ' * (20 - complete)
                                sys.stdout.write(
                                    f'\r[{fill_c}{unfill_c}] ⚡ {round(dl / full_length * 100, 1)} % ⚡ {round(dl / 1000000, 1)} / {round(full_length / 1000000, 1)} MB')
                                sys.stdout.flush()


                    command = R'"C:\Program Files (x86)\Electric\updater\updater.exe"'

                    Popen(command, close_fds=True, shell=True)
                    click.echo(click.style('\nSuccessfully Updated Electric!', fg='green'))
                    sys.exit()
                else:
                    click.echo(click.style('Re-Run Electric As Administrator To Update', fg='red'))


def check_supercache_valid():
    filepath = Rf'{appdata_dir}\superlog.txt'
    if os.path.isfile(filepath):
        with open(filepath, 'r') as f:
            contents = f.read()
        date = datetime.strptime(contents, '%Y-%m-%d %H:%M:%S.%f')
        if (datetime.now() - date).days < 7:
            return True
        else:
            return False
    with open(filepath, 'w+') as f:
        f.write(str(datetime.strptime(str(datetime.now()), '%Y-%m-%d %H:%M:%S.%f')))
    return True

def check_supercache_availiable(package_name: str) -> bool:
    supercache_dir = PathManager.get_appdata_directory() + R'\SuperCache'
    files = os.listdir(supercache_dir)
    if f'{package_name}.json' in files:
        return True
    return False


def handle_cached_request(package_name: str):
    start = timer()
    supercache_dir = PathManager.get_appdata_directory() + R'\SuperCache'
    try:
        with open(rf'{supercache_dir}\{package_name}.json') as f:
            res = json.load(f)
    except FileNotFoundError:
        return 'NOT FOUND', 1
    end = timer()
    return res, (end - start)


def generate_metadata(no_progress, silent, verbose, debug, no_color, yes, logfile, virus_check, reduce, rate_limit, settings, sync, no_cache):
    return Metadata(no_progress, no_color, yes, silent, verbose, debug, logfile, virus_check, reduce, rate_limit, settings, sync, no_cache)


def disp_error_msg(messages: list, metadata: Metadata):
    if 'no-error' in messages:
        return

    reboot = False
    websites = []
    commands = []
    support_ticket = False
    idx = 0
    for msg in messages:
        if idx == 0:
            click.echo(click.style(msg, fg='yellow'))
            idx += 1
            continue
        if 'Reboot' in msg:
            reboot = True
            break
        if 'http' in msg:
            websites.append(msg.strip())
            click.echo(click.style(msg, fg='blue'))
            idx += 1
            continue
        if 'electric install' in msg:
            commands.append(re.findall(r'\`(.*?)`', msg))
        if 'NAME' and 'VERSION' in msg:
            click.echo(click.style(msg, fg='green'))
            support_ticket = True
            break
        else:
            click.echo(msg)

        idx += 1

    if support_ticket:
        click.echo('By sending a support ticket, you agree to the Terms And Conditions (https://www.electric.sh/support/terms-and-conditions)')
        sending_ticket = click.confirm('Would you like to send the support ticket ?')
        if sending_ticket:
            with Halo('', spinner='bounce') as h:
                res = requests.post('https://electric-package-manager.herokuapp.com/windows/support-ticket/', json={'Logs': get_recent_logs()})
                if res.status_code == 200:
                    h.stop()
                    click.echo(click.style('Successfully Sent Support Ticket!', fg='green'))
                else:
                    h.fail('Failed To Send Support Ticket')

    if reboot:
        reboot = click.confirm('Would you like to reboot?')
        if reboot:
            os.system('shutdown /R')

    if commands:
        run = click.confirm('Would You Like To Install Node?')
        if run:
            print('\n')
            os.system(commands[0][0])

    if websites:
        website = click.confirm('Would You Like To Visit Any Of The Above Websites?')
        if website:
            try:
                webpage = int(click.prompt('Which Webpage Would You Like To Visit? ')) - 1
            except:
                handle_exit('ERROR', None, metadata)
            try:
                webbrowser.open(websites[webpage][8:])
            except:
                pass
    handle_exit('ERROR', None, metadata)


def get_error_message(code: str, method: str, display_name: str, version: str):
    attr = method.replace('ation', '')
    with Switch(code) as code:
        if code('0001'):
            return [
                f'\n[0001] => {method.capitalize()} failed because the software you tried to {attr} requires administrator permissions.',
                f'\n\nHow To Fix:\n\nRun Your Command Prompt Or Powershell As Administrator And Retry {method.capitalize()}.\n\nHelp:',
                '\n[1] <=> https://www.howtogeek.com/194041/how-to-open-the-command-prompt-as-administrator-in-windows-8.1/',
                '\n[2] <=> https://www.top-password.com/blog/5-ways-to-run-powershell-as-administrator-in-windows-10/\n\n'
                f'If that doesn\'t work, please file a support ticket at => https://www.electric.sh/support\n'
            ]

        elif code('0002'):
            return [
                f'\n[0002] => {method.capitalize()} failed because the installer provided an incorrect command for {method}.',
                '\nWe recommend you raise a support ticket with the data generated below:',
                generate_report(display_name, version),
                '\nHelp:\n',
                'https://www.electric.sh/troubleshoot'
            ]

        elif code('0000'):
            return [
                f'\n[0000] => {method.capitalize()} failed due to an unknown reason.',
                '\nWe recommend you raise a support ticket with the data generated below:',
                generate_report(display_name, version),
                '\nHelp:',
                f'\n[1] <=> https://www.electric.sh/troubleshoot'
            ]

        elif code('0011'):
            clipboard.copy('electric install nodejs')
            return [
                '\n[0011] => Node(npm) is not installed on your system.',
                '\n\nHow To Fix:\n',
                'Run `electric install nodejs` [ Copied To Clipboard ] To Install Node(npm)'
            ]

        elif code('1603'):
            return [
                f'\n[1603] => {method.capitalize()} might have failed because the software you tried to {attr} might require administrator permissions. \n\nIf you are running this on an administrator terminal, then this indicates a fatal error with the installer itself.',
                f'\n\nHow To Fix:\n\nRun Your Command Prompt Or Powershell As Administrator And Retry {method.capitalize()}.\n\nHelp:',
                '\n[1] <=> https://www.howtogeek.com/194041/how-to-open-the-command-prompt-as-administrator-in-windows-8.1/',
                '\n[2] <=> https://www.top-password.com/blog/5-ways-to-run-powershell-as-administrator-in-windows-10/\n\n',
            ]

        elif code('0010'):
            clipboard.copy('electric install python3')
            return [
                '\n[0010] => Python(pip) is not installed on your system.',
                '\n\nHow To Fix:\n',
                'Run `electric install python3` [ Copied To Clipboard ] To install Python(pip).\n\nHelp:',
                '\n[1] <=> https://www.educative.io/edpresso/how-to-add-python-to-path-variable-in-windows',
                '\n[2] <=> https://stackoverflow.com/questions/23708898/pip-is-not-recognized-as-an-internal-or-external-command'
                ]

        elif code('1010'):
            return [
                f'\n[1010] => Installer Has Requested A Reboot In Order To Complete {method.capitalize()}.\n'
            ]

        elif code('1111'):
            return [
                f'\n[1111] => The {attr.capitalize()}er For This Package Failed Due To A Fatal Error. This is likely not an issue or error with electric.',
                '\n\nWe recommend you raise a support ticket with the data generated below:',
                generate_report(display_name, version),
                '\nHelp:\n',
                '\n[1] <=> https://www.electric.sh/errors/1111',
                '\n[2] <=> https://www.electric.sh/support',
            ]

        elif code('0101'):
            return [
                f'\n[0101] => The installer / uninstaller was denied of Administrator permissions And failed to initialize successfully.',
                '\n\nHow To Fix:\n',
                'Make sure you accept prompt asking for administrator privileges or alternatively: \n',
                f'Run Your Command Prompt Or Powershell As Administrator And Retry {method.capitalize()}.\n\n\nHelp:',
                '\n[1] <=> https://www.electric.sh/errors/0101',
                '\n[2] <=> https://www.howtogeek.com/194041/how-to-open-the-command-prompt-as-administrator-in-windows-8.1/',
                '\n[3] <=> https://www.top-password.com/blog/5-ways-to-run-powershell-as-administrator-in-windows-10/\n\n'
            ]


def handle_unknown_error(err: str):
    error_msg = click.confirm('Would You Like To See The Error Message?')

    if error_msg:
        print(err + '\n')
        with Halo('Troubleshooting ', text_color='yellow'):
            results = search(query=err, stop=3)
            results = [f'\n\t[{index + 1}] <=> {r}' for index, r in enumerate(results)]

            results = ''.join(results)

            if '.google-cookie' in os.listdir('.'):
                os.remove('.google-cookie')

        print(f'These automatically generated links may help:{results}')


    proc = Popen('tasklist', stdin=PIPE, stdout=PIPE, stderr=PIPE)
    output, err = proc.communicate()
    output = output.decode('utf-8')
    lines = output.splitlines()

    cleaned_up_names = []
    for line in lines:
        try:
            cleaned_up_names.append(line.split()[0].strip('.exe'))
        except IndexError:
            continue

    count = 0
    for name in cleaned_up_names:
        if name == 'powershell' or name == 'cmd':
            count += 1

    return count >= 2


def display_info(res: dict, nightly: bool = False, version: str = '') -> str:
    pkg = res
    keys = list(pkg.keys())
    idx = 0

    if not version:
        for key in keys:
            if key not in ['package-name', 'nightly', 'display-name']:
                idx = keys.index(key)
                break
        version = keys[idx]
    if nightly:
        version = 'nightly'
    try:
        pkg = pkg[version]
    except KeyError:
        name = res['display-name']
        click.echo(click.style(f'\nCannot Find {name}::v{version}', 'red'))
        exit()
    url = pkg['url']
    display_name = res['display-name']
    package_name = res['package-name']
    calc_length = len(f'{Fore.MAGENTA}│ {Fore.GREEN}Url(Windows) {Fore.MAGENTA}=> {Fore.CYAN}{url}{Fore.CYAN}{Fore.MAGENTA}│') - 30
    name_line = len(f'{Fore.MAGENTA}│ {Fore.GREEN}Name {Fore.MAGENTA}=>{display_name}{Fore.GREEN}{Fore.YELLOW}{Fore.MAGENTA}') - 30
    version_line = len(f'{Fore.MAGENTA}│{Fore.GREEN}Latest Version {Fore.MAGENTA}=>{Fore.BLUE}{version}{Fore.GREEN}{Fore.MAGENTA}│') - 30
    url_line = len(f'{Fore.MAGENTA}│ {Fore.GREEN}Url(Windows){Fore.MAGENTA}=>{Fore.CYAN}{url}{Fore.CYAN}{Fore.MAGENTA}│') - 30
    command_line = len(f'{Fore.MAGENTA}│ {Fore.GREEN}Install Command{Fore.MAGENTA}=>{Fore.CYAN}{package_name}{Fore.CYAN}{Fore.MAGENTA}│') - 13
    base = '─'
    return f'''
{Fore.MAGENTA}┌{base * calc_length}{Fore.MAGENTA}┐
{Fore.MAGENTA}| {Fore.GREEN}Name {Fore.MAGENTA}=>{Fore.GREEN}{Fore.YELLOW} {display_name}{Fore.MAGENTA}{' ' * (calc_length - name_line)}|
{Fore.MAGENTA}| {Fore.GREEN}Latest Version {Fore.MAGENTA}=> {Fore.BLUE}{version}{Fore.GREEN}{Fore.MAGENTA}{' ' * (calc_length - version_line)}|
{Fore.MAGENTA}| {Fore.GREEN}Url(Windows) {Fore.MAGENTA}=> {Fore.CYAN}{url}{Fore.CYAN}{Fore.MAGENTA}{' ' * (calc_length - url_line)}|
{Fore.MAGENTA}| {Fore.GREEN}Install Command {Fore.MAGENTA}=> {Fore.CYAN}electric install {package_name}{Fore.CYAN}{Fore.MAGENTA}{' ' * (calc_length - command_line)}|
{Fore.MAGENTA}└{base * calc_length}{Fore.MAGENTA}┘
'''


def get_correct_package_names(all=False) -> list:
    if not all:
        with open(rf'{PathManager.get_appdata_directory()}\SuperCache\packages.json', 'r') as f:
            dictionary = json.load(f)
            packages = dictionary['packages']
    else:
        req = requests.get('https://electric-package-manager.herokuapp.com/setup/name-list')
        res = json.loads(req.text)
        packages = res['packages']

    return packages


def register_package_success(packet: Packet, install_dir: str, metadata: Metadata):
    data = {
        'display-name': packet.display_name,
        'json-name': packet.json_name,
        'version': packet.version,
        'custom-location-switch': packet.custom_location,
        'custom-install-directory': packet.directory if packet.directory else '',
        'flags': get_install_flags(install_dir, metadata)
    }
    pkg_dir = PathManager.get_appdata_directory() + r'\Current'
    with open(rf'{pkg_dir}\{packet.json_name}.json', 'w+') as f:
        f.write(json.dumps(data, indent=4))
    
    
def get_autocorrections(package_names: list, corrected_package_names: list, metadata: Metadata) -> list:
    corrected_names = []

    for name in package_names:
        if name in corrected_package_names:
            corrected_names.append(name)
        else:
            corrections = difflib.get_close_matches(name, corrected_package_names)
            if corrections:
                if metadata.silent and not metadata.yes:
                    click.echo(click.style(
                        'Incorrect / Invalid Package Name Entered. Aborting Installation.', fg='red'))
                    log_info(
                        'Incorrect / Invalid Package Name Entered. Aborting Installation', metadata.logfile)

                    handle_exit('ERROR', None, metadata)
                else:
                    corrected_names.append(corrections[0])

                if metadata.yes:
                    write_all(f'Autocorrecting To {corrections[0]}', 'bright_magenta', metadata)
                    write(
                        f'Successfully Autocorrected To {corrections[0]}', 'green', metadata)
                    log_info(
                        f'Successfully Autocorrected To {corrections[0]}', metadata.logfile)
                    corrected_names.append(corrections[0])

                else:
                    write_all(f'Autocorrecting To {corrections[0]}', 'bright_magenta', metadata)

                    if click.confirm('Would You Like To Continue?'):
                        package_name = corrections[0]
                        corrected_names.append(package_name)
                    else:
                        handle_exit('ERROR', None, metadata)
            else:
                req = requests.get('https://electric-package-manager.herokuapp.com/setup/name-list')
                res = json.loads(req.text)
                if name not in res['packages']:
                    write_all(f'Could Not Find Any Packages Which Match {name}', 'bright_magenta', metadata)
                else:
                    corrected_names.append(name)

    return corrected_names