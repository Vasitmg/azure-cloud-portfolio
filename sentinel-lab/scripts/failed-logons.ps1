# failed-logons.ps1
# Runs INSIDE the lab VM (via az vm run-command) and creates failed logons
# (Windows event 4625) so the brute-force detection can be tested.
# It calls the Windows LogonUser API with an account that does not exist,
# against the VM itself. Nothing leaves the machine.

$user = "fakeadmin"
$attempts = 10

Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public static class LabLogon {
    [DllImport("advapi32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
    public static extern bool LogonUser(string user, string domain, string password,
        int logonType, int logonProvider, out IntPtr token);
}
"@

$LOGON32_LOGON_NETWORK = 3
$LOGON32_PROVIDER_DEFAULT = 0

for ($i = 1; $i -le $attempts; $i++) {
    $token = [IntPtr]::Zero
    $ok = [LabLogon]::LogonUser($user, $env:COMPUTERNAME, "Wrong-Password-$i",
        $LOGON32_LOGON_NETWORK, $LOGON32_PROVIDER_DEFAULT, [ref]$token)
    Write-Output ("Attempt {0}: {1}" -f $i, $(if ($ok) { "unexpected success" } else { "failed as expected" }))
    Start-Sleep -Seconds 2
}
Write-Output "Done: $attempts failed logons for $user"