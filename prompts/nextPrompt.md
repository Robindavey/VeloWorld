# VeloWorld — Next Work Prompt

## Completed This Session

- Added optional live hardware power input to dedicated demo page `frontend/demo.html`.
- New power source selector in top bar:
  - `Manual Slider`
  - `Power Meter / Trainer`
- Added `Connect Device` flow using Web Bluetooth:
  - Tries Cycling Power service (`cycling_power`) first.
  - Falls back to Fitness Machine service (`fitness_machine`, Indoor Bike Data 0x2AD2).
- Live power from connected device now drives simulation speed/HUD.
- When hardware source is selected, manual power slider is disabled.
- Added device status label in UI (`Manual`, `Connected`, `Connection failed`, etc.).

## Current Demo Behavior

- Manual mode still works exactly as before.
- Device mode uses latest received power value from BLE notifications.
- HUD and power zones use whichever power source is active.

## Notes / Constraints

- Web Bluetooth requires a compatible browser (Chrome/Edge) and secure context (`localhost` is OK).
- Actual BLE service/characteristic support varies by trainer/power meter firmware.
- FTMS Indoor Bike Data parsing currently includes a common subset with instantaneous power.

## Next Tasks

1. Add reconnect/disconnect button and device forget behavior.
2. Add signal timeout fallback (if no BLE packets for N seconds, hold/decay power safely).
3. Add ANT+ bridge option (outside browser via local bridge service) for broader device support.
4. Add inline troubleshooting panel for BLE permissions/service discovery failures.

## Session Rule

Always update `prompts/nextPrompt.md` at the end of each session with:
- what changed,
- what is running,
- what to do next.
