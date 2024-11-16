#!/usr/bin/env python3
import requests
import sys
from datetime import datetime, timedelta
import time

GOE_HOST="http://192.168.1.91"
EVCC_HOST="http://192.168.1.2:7070"
EVCC_LOADPOINT_ID=1

EXIT_OK=0
EXIT_WARNING=1
EXIT_CRITICAL=2

modelStatusDict = {
  0: "NotChargingBecauseNoChargeCtrlData",
  1: "NotChargingBecauseOvertemperature",
  2: "NotChargingBecauseAccessControlWait",
  3: "ChargingBecauseForceStateOn",
  4: "NotChargingBecauseForceStateOff",
  5: "NotChargingBecauseScheduler",
  6: "NotChargingBecauseEnergyLimit",
  7: "ChargingBecauseAwattarPriceLow",
  8: "ChargingBecauseAutomaticStopTestLadung",
  9: "ChargingBecauseAutomaticStopNotEnoughTime",
  10: "ChargingBecauseAutomaticStop",
  11: "ChargingBecauseAutomaticStopNoClock",
  12: "ChargingBecausePvSurplus",
  13: "ChargingBecauseFallbackGoEDefault",
  14: "ChargingBecauseFallbackGoEScheduler",
  15: "ChargingBecauseFallbackDefault",
  16: "NotChargingBecauseFallbackGoEAwattar",
  17: "NotChargingBecauseFallbackAwattar",
  18: "NotChargingBecauseFallbackAutomaticStop",
  19: "ChargingBecauseCarCompatibilityKeepAlive",
  20: "ChargingBecauseChargePauseNotAllowed",
  22: "NotChargingBecauseSimulateUnplugging",
  23: "NotChargingBecausePhaseSwitch",
  24: "NotChargingBecauseMinPauseDuration",
  26: "NotChargingBecauseError",
  27: "NotChargingBecauseLoadManagementDoesntWant",
  28: "NotChargingBecauseOcppDoesntWant",
  29: "NotChargingBecauseReconnectDelay",
  30: "NotChargingBecauseAdapterBlocking",
  31: "NotChargingBecauseUnderfrequencyControl",
  32: "NotChargingBecauseUnbalancedLoad",
  33: "ChargingBecauseDischargingPvBattery",
  34: "NotChargingBecauseGridMonitoring",
  35: "NotChargingBecauseOcppFallback"
}
frcDict = {
  0: "Neutral",
  1: "Off",
  2: "On"
}
carDict = {
  0: "Unknown/Error",
  1: "Idle",
  2: "Charging",
  3: "WaitCar",
  4: "Complete",
  5: "Error"
}

def evcc_load_state():
  url = f'{EVCC_HOST}/api/state'
  response = requests.get(url)
  response.raise_for_status()
  data = response.json()
  return data["result"]

def evcc_get_loadpoint(state):
  return  state["loadpoints"][EVCC_LOADPOINT_ID-1]

def evcc_set_soc_limit(limit):
  print(f'Setting evcc soc_limit={limit}...')
  url = f'{EVCC_HOST}/api/loadpoints/{EVCC_LOADPOINT_ID}/limitsoc/{limit}'
  response = requests.post(url)
  response.raise_for_status()

def evcc_set_charge_mode(mode):
  print(f'Setting evcc charge mode={mode}...')
  url = f'{EVCC_HOST}/api/loadpoints/{EVCC_LOADPOINT_ID}/mode/{mode}'
  response = requests.post(url)
  response.raise_for_status()

def evcc_wait_charging(expected, timeout):
  for i in range(timeout):
    try:
      lp = evcc_get_loadpoint(evcc_load_state())
      charging = lp["charging"]
      print(f'  {i}: is={charging}, goal={expected}')
      if charging == expected:
        return True
      time.sleep(1)
    except Exception as e:
      print(f"ERROR: {e}")
  return False


def set_force_state(state):
  url = f'{GOE_HOST}/api/set?frc={state}'
  print(f"Calling {url}...")
  try:
    response = requests.get(url)
  except Exception as e:
    print(f"Communication with {url} failed: {e}")

def get_state():
  # Define the URL of the API endpoint
  # https://github.com/goecharger/go-eCharger-API-v2/blob/main/apikeys-de.md for keys
  url = f'{GOE_HOST}/api/status?filter=rbt,car,alw,lmsc,lccfi,lccfc,lcctc,cdi,frc,modelStatus'
  response = requests.get(url)
  response.raise_for_status()
  data = response.json()
  return data

def deadline_expired(current_time, epoch, lastCarStateChangedFromCharging):
  print(f"Checking how long in \"complete\" state...")
  ms = lastCarStateChangedFromCharging or 0 # we only consider from charging, if this info is not available force wakeup 

  starttime = epoch + timedelta(milliseconds=ms) if ms > 0 else datetime.fromtimestamp(0)
  deadline = starttime + timedelta(hours=8)
  deadline_delta = deadline - current_time
  deepsleep = starttime + timedelta(hours=10)
  deepsleep_delta = deepsleep - current_time
  print(f"Considering {starttime.strftime('%Y-%m-%d %H:%M:%S')} in wake-up calculation.")
  print(f"Car will deep-sleep around {deepsleep.strftime('%Y-%m-%d %H:%M:%S')}. This is in {deepsleep_delta}.")
  print(f"Deadline for wakeup charge is {deadline.strftime('%Y-%m-%d %H:%M:%S')}. This is in {deadline_delta}.")
  return deadline < current_time

def wake_via_goe():
  print()
  print("Waking car via go-echarger...")
  print("Forcing state ON...")
  set_force_state(2)
  # wait up to 60 seconds until car starts charging
  print("Waiting up to 60 seconds for car to actually start charging...")
  for i in range(60):
    new_state = get_state();
    new_car_state = new_state.get("car", -1)
    print(f"  {i}: car={carDict.get(new_car_state, new_car_state)}")
    if new_car_state == 2:
      print(f"Charging started, this has woken up the car. We are done.")
      print(f"Charging for 2 minutes.")
      time.sleep(2 * 60)
      break;
    time.sleep(1)

  print("Forcing state OFF again...")
  set_force_state(1)
  print("All should be good for the next 10 hours.")

def wake_via_evcc(old_mode, old_soc_limit):
  print()
  print("Waking car via evcc charge with minpv->100%...")
  evcc_set_soc_limit(100)
  evcc_set_charge_mode("minpv")
  print("Waiting for charge to be started...")
  if (evcc_wait_charging(True, 180)):
    print(f"Let charge continue for 5 minutes at minpv...")
    time.sleep(5 * 60)
  print(f"Resetting to soc_limit={old_soc_limit}...")
  evcc_set_soc_limit(old_soc_limit)
  print(f"Stopping charge now.")
  evcc_set_charge_mode("off")
  print("Waiting for charging to be stopped...")
  evcc_wait_charging(False, 180)
  print(f"Resetting to mode={old_mode}")
  evcc_set_charge_mode(old_mode)

###################### MAIN LOGIC ##########################

# Call the function to get the state data
# go-eCharger
state = get_state()
timeSinceReboot = state["rbt"]
carState = state["car"] # Unknown/Error=0, Idle=1, Charging=2, WaitCar=3, Complete=4, Error=5
carStateString = carDict.get(carState, f"UNKNOWN ({carState})")
carAllowedToLoad = state["alw"] # 0=False, 1=True
lastModelChange = state["lmsc"]
lastCarStateChangedFromIdle = state["lccfi"]
lastCarStateChangedFromCharging = state["lccfc"]
lastCarStateChangedToCharging = state["lcctc"]
modelStatus = state["modelStatus"]
modelStatusString = modelStatusDict.get(modelStatus, f"UNKNOWN ({modelStatus})")
forceState = state["frc"]
forceStateName = frcDict.get(forceState, f"UNKNOWN ({forceState})")

# evcc
evcc_state = evcc_load_state()
lp = evcc_get_loadpoint(evcc_state)
lp_mode = lp["mode"]
lp_connected = lp["connected"]
lp_charging = lp["charging"]
lp_soc_limit = lp["limitSoc"]
lp_vehicle_soc = lp["vehicleSoc"]

######### SHOW DATA USED FOR DECISSION MAKING #########

print(f"Raw data: {state}")
print()
print(f"Model Status:   {modelStatusString} ({modelStatus})")
print(f"Force State:    {forceStateName} ({forceState})")
print(f"Charging State: {carStateString}")
print()

current_time = datetime.now()
epoch = current_time - timedelta(milliseconds=timeSinceReboot)
important_timestamps = {
  "now": current_time,
  "reboot": epoch,
  "lastCarStateChangedFromIdle": (epoch + timedelta(milliseconds=lastCarStateChangedFromIdle)) if lastCarStateChangedFromIdle else None,
  "lastCarStateChangedFromCharging": (epoch + timedelta(milliseconds=lastCarStateChangedFromCharging)) if lastCarStateChangedFromCharging else None,
  "lastCarStateChangedToCharging": (epoch + timedelta(milliseconds=lastCarStateChangedToCharging)) if lastCarStateChangedToCharging else None,
}
important_timestamps_sorted_by_time = sorted(important_timestamps.items(), key=lambda e: e[1] or datetime.fromtimestamp(0))
# Print the time of each event in the past
for event, event_time in important_timestamps_sorted_by_time:
  if event_time:
    print(f"{event_time.strftime('%Y-%m-%d %H:%M:%S')}: {event}")
print()
print("=" * 72)
print()
print(f"EVCC Loadpoint: mode={lp_mode}, connected={lp_connected}, charging={lp_charging}")
print(f"EVCC SoC: vehicle={lp_vehicle_soc}%, limit={lp_soc_limit}%")
print()
print("=" * 72)
print()

######### DECISSION MAKING #########
try:
  if carState== 1:
    print("No car connected to charger.")
  if carState == 2 or forceState == 2:
    print("Currently charging or charge already forced.")
  elif carState == 3 or carState == 4: # waitCar or complete, but no charging forced yet
    if (deadline_expired(current_time=current_time, epoch=epoch, lastCarStateChangedFromCharging=lastCarStateChangedFromCharging)):
      if forceState == 1:
        if (lp_mode == "pv" or lp_mode == "off") and lp_vehicle_soc <= 99 :
          wake_via_evcc(old_mode=lp_mode, old_soc_limit=lp_soc_limit)
        else:
          # don't know if we can do it via evcc, trigger directly at go-echarger
          wake_via_goe()
        sys.exit(EXIT_WARNING) # I want cron-mails for now!
      elif forceState == 2:
        print("Already forced on, nothing to do...")
      else:
        print(f"forceState is {forceStateName} ({forceState}), don't know how to handle.")
        sys.exit(EXIT_CRITICAL)
    else:
      print("Nothing to do. Waiting for deadline to expire.")
  else:
    print(f"Don't know how to handle carState={carStateString} ({carState}). Help!")
    sys.exit(EXIT_CRITICAL)
except Exception as e:
  print(f"CRITICAL: Exception: {e}")
  sys.exit(EXIT_CRITICAL)
