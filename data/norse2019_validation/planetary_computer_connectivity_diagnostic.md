# Planetary Computer Windows Connectivity Diagnostic

**Project:** `E:\OneDrive\Desktop\Hackathon material\PCCOE IGC\Oil_Spill`  
**Host:** `planetarycomputer.microsoft.com`  
**Diagnostic window:** 2026-11-07 01:21:31–01:21:35 Asia/Calcutta (UTC+05:30)  
**Scope:** DNS, TCP port 443, and conditional metadata-only HTTPS request. No raster or asset was accessed.

## Results

| Check | Outcome |
|---|---|
| DNS A lookup (`Resolve-DnsName`) | Failed locally with `System.ComponentModel.Win32Exception: planetarycomputer.microsoft.com : Access is denied.` No address returned. |
| Windows/.NET system name resolver | Failed with `No such host is known.` No address returned. |
| TCP connectivity to port 443 (`Test-NetConnection`) | Not established. `NameResolutionSucceeded: False`, `TcpTestSucceeded: False`, no remote address. Since name resolution failed, this does not establish a TCP-level refusal or timeout. |
| STAC collection HTTPS request | Skipped as requested because DNS did not resolve. No HTTP status or response body. |

The failure occurs at local hostname resolution, before a TCP connection or TLS/HTTP exchange. The available evidence does **not** distinguish a local DNS server/configuration problem from a runtime or network policy that blocks DNS lookup; `Resolve-DnsName` specifically reports access denied, while the system resolver reports no host known. It is not evidence that Planetary Computer returned an HTTP error or that the endpoint is unavailable.

## Exact commands and captured output

Commands were run in PowerShell from the project root. The diagnostic bracket started at `2026-11-07T01:21:31.4410475+05:30` and ended at `2026-11-07T01:21:35.3441947+05:30`.

1. `Resolve-DnsName planetarycomputer.microsoft.com -Type A`

   Result: `System.ComponentModel.Win32Exception: planetarycomputer.microsoft.com : Access is denied.`

2. `[System.Net.Dns]::GetHostAddresses('planetarycomputer.microsoft.com')`

   Result: `System.Management.Automation.MethodInvocationException: Exception calling "GetHostAddresses" with "1" argument(s): "No such host is known."`

3. `Test-NetConnection planetarycomputer.microsoft.com -Port 443 -InformationLevel Detailed`

   Relevant result fields:

   ```text
   ComputerName            : planetarycomputer.microsoft.com
   RemoteAddress           :
   RemotePort              : 0
   NameResolutionSucceeded : False
   TcpTestSucceeded        : False
   InterfaceAlias          :
   SourceAddress           :
   ```

4. Conditional request, not run because DNS failed:

   `Invoke-WebRequest -Uri "https://planetarycomputer.microsoft.com/api/stac/v1/collections/sentinel-1-rtc" -Method Get -TimeoutSec 20`

   Result: skipped; no HTTP status was obtained.

## Interpretation and next diagnostic step

This run only establishes that this Windows execution environment could not resolve the hostname at the time of the check. TCP/443 and HTTPS remain untested because the checks depend on successful name resolution. Retry the three network checks from a normal user PowerShell session on a network with DNS access. If `Resolve-DnsName` still reports access denied while another approved network environment resolves the host, investigate local endpoint/network policy with the device administrator; this diagnostic did not change DNS settings or network configuration.

No project source, scene metadata, benchmark output, or data files were changed. No scene fetcher/bootstrap command, raster download, package installation, or DNS configuration change was performed.
