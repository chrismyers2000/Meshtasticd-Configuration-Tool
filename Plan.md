# Project Title: Meshtasticd Configuration Tool

## What is it?
This is an application to install AND configure meshtasticd (the linux-native version of meshtastic). It will be used to setup and configure meshtasticd for use with the
MeshAdv Pi Hat v1.1, MeshAdv Mini, and MeshAdv Pro(not released yet but shares similar specs as the mini and needs to be added)

## Requirements:
- Architecture: Works on Raspberry pi (2,3,4,5,400,500,Zero 2w), needs to support raspberry pi OS bookworm and trixie
- Python based, with a mix of bash commands.
- Gui based, with ability to run in the command line (does this need to be a separate app? Strike this line if the answer is yes)
- Must be easily installable by using a curl command. This will be uploaded to github and I want it to be easy to install for new users. example: "curl -fsSL https://github.com/chrismyers2000/install.sh | bash" 
- installation  script will check for and install needed dependancies, updating them if needed. 
- Check ExampleGui.png for an idea of the general GUI layout. This does not need to be stricktly followed. This design layout may change throughout the project.
- The command line app will be a TUI style. It needs to work remotely over SSH, Putty, and from Windows ssh. (also  strike this  line if the command line app needs to be a separate app)

## Hardware Infomation:
1. Detect which raspberry pi we have
2. Detect which meshadv pi hat is installed, if none is detected, we may have a MeshAdv Pi Hat v1.1 as it has no EEPROM.
3. Detect which version of meshtasticd is installed if any

## Functions: 
Note: Each function will be performed by clicking a button. Next to each button will be the status of the function, status needs to stay up to date. If any of these  are
performed, add a message to  the bottom of the app saying that a reboot is required for settings to take place.

1. "Install/Remove meshtasticd" When the button is clicked, display a pop up window with the rest of the function. we need to determine if we are running 32bit or 64bit. 
If 32bit we  will use the raspbian repos and 64bit will use the debian repos.
The following is the example bash command that is given by the official meshtasticd docs to install for 32bit trixie:

[[ "$(. /etc/os-release && echo $NAME)" != Raspbian* ]] && echo "ERROR: Raspberry Pi OS (32-bit) not detected, please use the Debian repos."
echo 'deb http://download.opensuse.org/repositories/network:/Meshtastic:/beta/Raspbian_13/ /' | sudo tee /etc/apt/sources.list.d/network:Meshtastic:beta.list
curl -fsSL https://download.opensuse.org/repositories/network:Meshtastic:beta/Raspbian_13/Release.key | gpg --dearmor | sudo tee /etc/apt/trusted.gpg.d/network_Meshtastic_beta.gpg > /dev/null
sudo apt update
sudo apt install meshtasticd

notice this is for the beta version, we need to also have options to install the alpha and daily versions for all of the repos.

This is the example command for 64bit trixie:

[[ "$(. /etc/os-release && echo $NAME)" == Raspbian* ]] && echo "ERROR: Raspberry Pi OS (32-bit) detected, please use the Raspbian repos."
echo 'deb http://download.opensuse.org/repositories/network:/Meshtastic:/beta/Debian_13/ /' | sudo tee /etc/apt/sources.list.d/network:Meshtastic:beta.list
curl -fsSL https://download.opensuse.org/repositories/network:Meshtastic:beta/Debian_13/Release.key | gpg --dearmor | sudo tee /etc/apt/trusted.gpg.d/network_Meshtastic_beta.gpg > /dev/null
sudo apt update
sudo apt install meshtasticd

we can probably get rid of the first line for both of these examples since all it does is detect the OS.
trixie is 13 and bookworm is 12.
For uninstalling,  use the purge function.

2. "Enable SPI" check /boot/firmware/config.txt for these lines:

dtparam=spi=on
dtoverlay=spi0-0cs

If they are not present, add them. 

3. "Enable I2C" check /boot/firmware/config.txt for this line:

dtparam=i2c_arm=on

add it if not present.

4. "Enable GPS/UART" check /boot/firmware/config.txt for this line:

enable_uart=1 # Needed for all Pi devices.
dtoverlay=uart0 # Needed for the Pi 5 or 500.

add them if not present, pay attention to the comments, one line is for pi 5 and 500 only.
add these lines if a MeshAdv Mini or MeshAdv Pro hat has been detected:

dtoverlay=pps-gpio,gpiopin=17 #Enables PPS
gpio=4=op,dh #Enables GPS Enable pin

check /etc/meshtasticd/config.yaml to see if this setting is uncommented:

GPS:
  SerialPath: /dev/ttyS0
  
Uncomment or add if not already and make sure /dev/ttyS0 is specified for all pi's  except  the 5 and 500.
If we have a pi 5  or 500 then /dev/ttyAMA0 is the device we need.
 
5. "Set Hat Config" This will open a popup window  to select which config file from /etc/meshtasticd/available.d should be copied to /etc/meshtasticd/config.d
Some of the files are grouped in folders so we need to be able to open those folders to select the file. 

Note: lora-MeshAdv-900M30S.yaml is for the MeshAdv Pi Hat v1.1, if no hat is detected, consider this the default selection, highlight it for the user.
lora-MeshAdv-Mini-900M22S.yaml is for the MeshAdv Mini.
The MeshAdv Pro does not have a file affiliated with it yet but will be very similar to the mini.

Add an option next to the lora-MeshAdv-Mini-900M22S.yaml file to download from the Frequency Labs github repo in case the file 
is not availible  or not working.
https://github.com/chrismyers2000/MeshAdv-Mini/blob/129451abcf4199af48312efcf6ecafa16712d675/Data/lora-MeshAdv-Mini-900M22S.yaml is the location for lora-MeshAdv-Mini-900M22S.yaml
 
6. "Edit Config" Clicking this will allow the user to edit the /etc/meshtasticd/config.yaml file in their editor choice. Give the option to open it in nano in a new terminal

## Actions
These are all buttons as well and need  to show the status next them just  like the functions buttons.

1. "systemctl options" open a popup window with these options:

Enable the service to start on boot:

sudo systemctl enable meshtasticd

Start the service:

sudo systemctl start meshtasticd

Check the status of the service:

sudo systemctl status meshtasticd

This will give you a detailed view of the service status and any potential errors.

Stop the service:

sudo systemctl stop meshtasticd

Make sure there is a window that will display the output when selecting status command.

2. "Install Python CLI" This  will install the meshtastic python cli

The following in parenthesis is from the official meshtastic docs:

(Check that your computer has Python 3 installed.

Use the command
python3 -V

If this does not return a version, install python
sudo apt-get update
sudo apt-get install python3

Pip is typically installed if you are using python 3 version >= 3.4

Check that pip is installed using this command
pip3 -V

If this does not return a version, install pip
sudo apt-get install python3-pip

Optional: use a python virtual environment (otherwise jump to step "Install pytap2")

Install python-virtualenvwrapper (arch based distros as an example)
sudo pacman -Syu python-virtualenvwrapper

Create a virtual environment
source /usr/bin/virtualenvwrapper.sh
mkvirtualenv meshtastic
workon meshtastic

Install pytap2

pip3 install --upgrade pytap2

Install meshtastic:

pip3 install --upgrade "meshtastic[cli]"

(the [cli] suffix installs a few optional dependencies that match older versions of the CLI)

Using pipx as an alternative to pip3 if externally-managed-environment error is encountered
sudo apt install pipx && pipx install "meshtastic[cli]"

If using pipx it may be necessary to update $PATH by running:
pipx ensurepath

You may need to close and re-open the CLI. The path variables may or may not update for the current session when installing.
)

I personally have had trouble when trying to enable the virtual environment. not sure its the best way, maybe  skip that part.

3. "Set Region" Use the meshtastic CLI to set the region. I may need to  figure out the command  for this.

4. "Send Message" Use the meshtastic  CLI to  send a test message to the default channel. I may need to figure  out the command  for this.

## Final notes

create a file called ToDo.md for any loose ends so I know what things still need to be done. I know for example that I dont know the URL for the installation script yet so  add that in 
this file. Tell me breifly what needs to be done to which file,  and leave me a code line number so  i can  find it  easily.

Feel free to ask me any questions before you start building.
If you need to keep track of your progress, you can create a progress.md file that you can use as a checklist. read the file if you arent sure of your progress. check things off once they are completed. keep this file short and to the point. no large code here.
