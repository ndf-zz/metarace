## This script will attempt to install Metarace applications
## in a Windows Subsystem for Linux
##
## You may need to modify your powershell execution policy
## See https://go.microsoft.com/fwlink/?LinkID=135170
## Recommended Setting, 	
## 			Set-ExecutionPolicy -ExecutionPolicy RemoteSigned  
## (you can revert to Restricted afterwards if rquired)
## Script must be run with administrative rights
##
## WSL Requires Virtual Machine Platform and will attempt to install from online sources
## Prerequisites - You must have a device that can run Hyper-V, including having bios support for Virtualisation.  See:
## 		https://learn.microsoft.com/en-us/windows-server/virtualization/hyper-v/system-requirements-for-hyper-v-on-windows
## 

# Ensure script is run as Administrator
if (-not ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(`
    [Security.Principal.WindowsBuiltInRole] "Administrator"))
{
    Write-Warning "Administrator rights required.`nPlease re-run as an Administrator."
    exit
}

# Define the path to your provisioning script
$MetaraceScript = "metarace-install.sh"
$MetaraceUrl = "https://github.com/ndf-zz/metarace/raw/refs/heads/master/metarace-install.sh"
$ProvisionScript = "wsl-provision.sh"
$ProvisionUrl = "https://github.com/ndf-zz/metarace/raw/refs/heads/master/wsl-provision.sh"
$ProvisionBasePathWin = "C:\temp\"
$ProvisionBasePathWSL = "/mnt/c/temp/"
$MetaracePathWin = $ProvisionBasePathWin + $MetaraceScript
$ProvisionPathWin = $ProvisionBasePathWin + $ProvisionScript
$ProvisionPathWSL = $ProvisionBasePathWSL + $ProvisionScript
$ProvisionMetarace = "sh " + $ProvisionPathWSL

# Check the feature status
$feature = Get-WindowsOptionalFeature -Online -FeatureName VirtualMachinePlatform

if ($feature.State -eq "Enabled") {
	Write-Output "VirtualMachinePlatform enabled."
} else {
	# Enable Hyper-V and required features
	Write-Output "Enabling VirtualMachinePlatform..."
	Enable-WindowsOptionalFeature -Online -FeatureName VirtualMachinePlatform -All -NoRestart
	Write-Output "VirtualMachinePlatform has been enabled. Please restart your computer to apply changes."
}


#Check if Hyper-V is enabled before continuing
$hyperV = systeminfo | Select-String "Hyper-V Requirements"
if ($hyperV -match "A hypervisor has been detected") {
    Write-Output "Virtualization is enabled."

	# Check if Debian is already installed
	$distributions = wsl --list --quiet
	if ($distributions -contains "Debian") {
		Write-Output "Debian installed in WSL."
	} else {
		Write-Output "Debian not installed. Installing Debian..."
		# Enable WSL and Virtual Machine Platform
		wsl --install --no-distribution

		# Wait for WSL installation to complete
		Start-Sleep -Seconds 10
		Write-Output "Debian installation initiated. Please wait for setup to complete.  You may need to type Exit [Enter] to continue script"
		wsl --install -d Debian
		Write-Output "WSL and Debian installation complete. You may need to restart your computer."
	}
	
} else {
    Write-Output "Virtualization not enabled or not supported."
	$hyperVReq = systeminfo | Select-String "Virtualization Enabled"
	Write-Output $hyperVReq
	exit 1
}


## Start metarace package install
if (-Not (Test-Path -Path $ProvisionBasePathWin)) {
	New-Item -ItemType Directory -Path $ProvisionBasePathWin
	Write-Output "Folder created at $ProvisionBasePathWin"
} else {
	Write-Output "Folder already exists at $ProvisionBasePathWin"
}

wget "$MetaraceUrl" -OutFile "$MetaracePathWin"
wget "$ProvisionUrl" -OutFile "$ProvisionPathWin"

# Check if the file exists
if (-Not (Test-Path $ProvisionPathWin)) {
	Write-Error "Provisioning script not found at $ProvisionScript"
	exit 1
}

# Run the provisioning script inside Debian WSL
wsl -d Debian -- bash -c $ProvisionMetarace

