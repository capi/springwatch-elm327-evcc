#!/usr/bin/env python3
from datetime import datetime, timedelta
import json
import requests
import sys
import time

GOE_HOST="http://192.168.1.91"
EVCC_HOST="http://192.168.1.2:7070"
EVCC_LOADPOINT_ID=1
TIMELINE_FILE="goe-keep-dacia-awake.timeline.json"

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

def deadline_expired(timeline):
  now = timeline["now"]
  deadline = timeline["deadline"]
  return deadline < now

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

def save_timeline(timeline):
  try:
    with open(TIMELINE_FILE, "w") as f:
      timeline_json = {}
      for key, value in timeline.items():
        if not key.endswith("_IGNORED"):
          timeline_json[key] = value.strftime('%Y-%m-%d %H:%M:%S')
      json.dump(timeline_json, f, indent=2, default=str)
  except Exception as e:
    print(f"Failed storing timeline.json, skipping: {e}")

def load_timeline():
  try:
    with open(TIMELINE_FILE, "r") as f:
      timeline_as_strings = json.load(f)
      timeline = {}
      for key, value in timeline_as_strings.items():
        timeline[key] = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
      return timeline
  except Exception as e:
    print(f"Failed loading timeline, starting with an empty timeline. Reason: {e}")
    return {}

def build_timeline():
  timeline = load_timeline()
  timeline["now"] = current_time
  timeline["reboot"] = epoch

  if lastCarStateChangedFromIdle:
    if "lastCarStateChangedFromIdle" not in timeline or lastCarStateChangedFromIdle >= 60*1000:
       # store it if there is no other information in the loaded timeline
       # or if it is clearly not reset due to a device reboot (within 60s of device reboot)
       timeline["lastCarStateChangedFromIdle"] = timeline["reboot"] + timedelta(milliseconds=lastCarStateChangedFromIdle)
    else:
      timeline["lastCarStateChangedFromIdle__IGNORED"] = timeline["reboot"] + timedelta(milliseconds=lastCarStateChangedFromIdle)
  if lastCarStateChangedFromCharging:
    timeline["lastCarStateChangedFromCharging"] = timeline["reboot"] + timedelta(milliseconds=lastCarStateChangedFromCharging)
  if lastCarStateChangedToCharging:
    timeline["lastCarStateChangedToCharging"] = timeline["reboot"] + timedelta(milliseconds=lastCarStateChangedToCharging)

  # calculate deadlines
  starttime = timeline.get("lastCarStateChangedFromCharging", datetime.fromtimestamp(0))
  if "lastCarStateChangedFromIdle" in timeline:
    diff_secs = abs(timeline["lastCarStateChangedFromIdle"] - timeline["reboot"]).total_seconds()
    if diff_secs > 60 and timeline["lastCarStateChangedFromIdle"] > starttime:
      print("Using lastCarStateChangedFromIdle {timeline['lastCarStateChangedFromIdle']} since it's the later event.")
      starttime = timeline["lastCarStateChangedFromIdle"]
  if "lastCarStateChangedToCharging" in timeline:
    if timeline["lastCarStateChangedToCharging"] > starttime:
      starttime = timeline["lastCarStateChangedToCharging"]

  deadline = starttime + timedelta(hours=8)
  deepsleep = starttime + timedelta(hours=10)
  # put calculated events into timeline
  timeline["deadline"] = deadline
  timeline["deepsleep"] = deepsleep

  save_timeline(timeline)
  return timeline

def sorted_timeline(timeline):
  return sorted(timeline.items(), key=lambda e: e[1] or datetime.fromtimestamp(0))

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

print(f"Raw go-eCharger data: {state}")
print()
print(f"Model Status:   {modelStatusString} ({modelStatus})")
print(f"Force State:    {forceStateName} ({forceState})")
print(f"Charging State: {carStateString}")
print()

current_time = datetime.now()
epoch = current_time - timedelta(milliseconds=timeSinceReboot)
timeline = build_timeline()

for event, event_time in sorted_timeline(timeline):
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
    if (deadline_expired(timeline)):
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
      time_remaining = timeline["deadline"] - timeline["now"]
      print(f"Nothing to do. Waiting for deadline to expire. Time remaining: {time_remaining}")
  else:
    print(f"Don't know how to handle carState={carStateString} ({carState}). Help!")
    sys.exit(EXIT_CRITICAL)
except Exception as e:
  print(f"CRITICAL: Exception: {e}")
  sys.exit(EXIT_CRITICAL)
