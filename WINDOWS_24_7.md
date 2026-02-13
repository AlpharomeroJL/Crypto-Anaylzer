# Keeping the PC up 24/7 (optional guidance)

Steps to reduce unexpected restarts while keeping Windows Update and security reasonable. **All changes are optional.** Apply only what you need.

---

## A) No auto-restart while a user is logged on

Windows can restart to finish updates even when someone is using the PC. These settings ask it not to restart automatically when a user is logged on (restarts may still be required later; you choose when).

### A1) Group Policy (Windows Pro / Enterprise)

1. Press **Win + R**, type **gpedit.msc**, press Enter.
2. Go to: **Computer Configuration** → **Administrative Templates** → **Windows Components** → **Windows Update**.
   - On Windows 11, look under **Legacy Policies** if you don’t see the policy at the top level.
3. Double‑click **“No auto-restart with logged-on users for scheduled automatic updates”**.
4. Select **Enabled** → OK.
5. Open an **elevated** Command Prompt or PowerShell and run:
   ```bat
   gpupdate /force
   ```

### A2) Registry fallback (e.g. Windows Home)

Use only if Group Policy is not available. **Back up the registry or create a restore point first.**

1. Press **Win + R**, type **regedit**, press Enter.
2. Go to: **HKEY_LOCAL_MACHINE\SOFTWARE\Policies\Microsoft\Windows**.
3. Create key **WindowsUpdate** (if it doesn’t exist).
4. Under **WindowsUpdate**, create key **AU** (if it doesn’t exist).
5. Under **AU**, create a **DWORD (32-bit)** value named **NoAutoRebootWithLoggedOnUsers**.
6. Set its value to **1**.
7. Reboot once for the change to take effect.

To undo later: set **NoAutoRebootWithLoggedOnUsers** to **0** or delete the value.

---

## B) Scheduled restart tasks (documentation only)

Windows Update can create scheduled tasks that perform restarts (e.g. “Schedule Work”, “Reboot”). You can **inspect** them; changing or disabling them can affect updates and is not recommended unless you know what you’re doing.

- Open **Task Scheduler** (taskschd.msc).
- Under **Task Scheduler Library**, look under **Microsoft → Windows → WindowsUpdate** (and related folders) for tasks that run after updates.
- Do **not** delete or disable tasks unless you accept the risk of delaying or breaking updates. Prefer **Active Hours** and **“No auto-restart with logged-on users”** (A1/A2) instead.

---

## Active Hours (built-in)

- **Settings → System → Windows Update → Advanced options** (or **Settings → Windows Update**).
- Set **Active hours** so Windows avoids restarting during those hours when possible.
- Note: Active hours do not always block restarts; they only reduce the chance. Combining with (A) gives stronger protection for logged-on use.

---

## Summary

- **Safest for 24/7 + security:** Use **Active Hours** and enable **“No auto-restart with logged-on users”** via Group Policy (A1) or registry (A2). Allow updates to install; you choose when to reboot.
- **Do not:** Turn off Windows Update entirely or remove update-related scheduled tasks unless you have a specific reason and understand the risks.
