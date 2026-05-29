#requires -Version 7.0
<#
.SYNOPSIS
    Deploys the all-in-one Azure Context Cache quickstart (AOAI + Cache + linked deployment).

.EXAMPLE
    ./deploy.ps1 -ResourceGroup rg-cc-demo
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)] [string]$ResourceGroup,
    [string]$Location = 'centralus',
    [string]$NamePrefix,
    [switch]$UseBicep
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot

if (-not (az group show --name $ResourceGroup 2>$null)) {
    Write-Host "Creating resource group $ResourceGroup in $Location..." -ForegroundColor Cyan
    az group create --name $ResourceGroup --location $Location | Out-Null
}

$template = if ($UseBicep) { Join-Path $root 'bicep/main.bicep' } else { Join-Path $root 'azuredeploy.json' }

$azArgs = @('deployment','group','create','--resource-group',$ResourceGroup,'--template-file',$template)
if ($NamePrefix) { $azArgs += @('--parameters',"namePrefix=$NamePrefix") }

az @azArgs
