# Windows - WSL/Debian Installation Instructions

## 1. Check and Enable Virtual Machine Platform
The PowerShell script verifies whether the **Virtual Machine Platform** Windows feature is enabled. If it is not, the script will attempt to enable it.

## 2. System Restart Requirement
If the feature is newly enabled, a **system restart** is typically required for virtualization support to become active.  

> ⚠️ The script will terminate at this point if it cannot proceed further.
> ⚠️ Note - if the script keeps stopping at this point, it maybe that you need to enable Virtualization support in the computer BIOS / UEFI.

## 3. Re-run the Script After Restart
After restarting your system, **re-execute the same PowerShell script** to continue the installation process.

## 4. Install WSL and Debian
The script will:

   - Install **WSL** if it is not already present.
   - Automatically download and install a **Debian** Linux distribution.

## 5. Set Up Debian User Credentials
During the Debian setup, a terminal session will launch prompting you to create a **username and password**.  

> 🔐 These credentials are **specific to Debian** and are **not** your Windows login details.

## 6. Return Control to Script
After setting your credentials, you may be left at a shell prompt.  

   - If this happens, type `exit` and press **Enter** to allow the script to resume.

## 7. Install Prerequisites and Metarace
The script will then:

   - Update the Debian environment.
   - Install required dependencies.
   - Launch the **Metarace installer**, prompting you to confirm various options.  

> ✅ It is generally recommended to answer **"Y"** to all prompts unless you have specific requirements.
