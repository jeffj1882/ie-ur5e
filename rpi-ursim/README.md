# URSim on a Raspberry Pi

Prebuilt, headless URSim host for a Pi 4 or Pi 5 with wired Ethernet. On first
boot the Pi installs Docker, qemu-user-static, and starts URSim bound on all
interfaces. Any Mac on the same subnet can point `ROBOT_IP` at `ursim.local`
(or the DHCP-assigned IP) and talk to it exactly like they would to the arm.

**Read this first — the honest warning:** URSim ships only an `amd64` image.
The Pi runs `arm64`, so the container is translated by `qemu-user-static`.
That's the same translator that crashes URControl with `Mutex error code 95`
on my Mac's colima VM, and this Pi image uses the same qemu. Strong
possibility you'll see the same fault — `docker logs ursim` will show it in
seconds. If so, the Pi plays fine for Dashboard + noVNC but RTDE / motion
will be dead, same as on the Mac. A Pi 5 with `box64` instead of qemu *might*
clear that bug; if plain qemu fails, open an issue and we'll iterate.

## Hardware

- Pi 4 (4 GB+) or Pi 5 — Pi 5 strongly preferred, URSim under emulation is CPU-heavy
- 16 GB+ SD card (or NVMe if your Pi has a PCIe/HAT)
- Wired Ethernet to the same LAN as your Mac (bare minimum is local-link)
- PoE or 27W USB-C PSU

## Build

```bash
cd rpi-ursim
./build.sh                      # produces ursim-pi.img (~7 GB uncompressed)

# Optional: set a custom first-login password (default is "ursim")
URSIM_PI_PASSWORD='something' ./build.sh
```

The script bakes every `~/.ssh/*.pub` into the image's `authorized_keys` so
you can `ssh ursim@ursim.local` the moment the Pi comes up.

## Flash

**Easy path — `rpi-imager`:**
1. Open Raspberry Pi Imager
2. "Choose OS" → "Use custom" → pick `ursim-pi.img`
3. "Choose Storage" → your SD card
4. Flash. Skip the Imager's own cloud-init options — our `user-data` is already baked in.

**CLI path — `dd`:**
```bash
diskutil list                               # find the SD card (e.g. disk4)
diskutil unmountDisk /dev/disk4
sudo dd if=ursim-pi.img of=/dev/rdisk4 bs=4m status=progress
diskutil eject /dev/disk4
```

## First boot

1. Insert the SD card, connect Ethernet, power on.
2. First boot takes ~10 minutes: apt install + `docker pull` of the ~2 GB URSim image.
3. When the LED stops thrashing, try:
   ```bash
   ping ursim.local
   ssh ursim@ursim.local
   docker logs ursim --tail 50
   ```
4. If URControl logged the mutex error (see honest-warning above), stop here.
   If it's quiet, you're good: point the Mac at it:
   ```bash
   export ROBOT_IP=ursim.local
   ie-ur5e-dash robotmode
   ie-ur5e-dash safetystatus
   open http://ursim.local:6080/vnc.html
   ```

## What's on the image

- Ubuntu Server 24.04.3 LTS (arm64, preinstalled raspi image)
- `docker.io` + `docker-compose-v2`
- `qemu-user-static` + `binfmt-support` registered persistently
- `avahi-daemon` so `ursim.local` resolves without DNS setup
- `/etc/systemd/system/ursim.service` → brings URSim up on boot
- `/opt/ursim/docker-compose.yml` → the compose spec (tagged `ursim_e-series:5.11`)
- `/opt/ursim/programs` → bind-mounted into the container at `/ursim/programs`

## Updating URSim tag

```bash
ssh ursim@ursim.local
sudo sed -i 's|ursim_e-series:5.11|ursim_e-series:5.14|' /opt/ursim/docker-compose.yml
sudo systemctl restart ursim
```

## Known issues

- **`Mutex error code 95` in URControl.log** — qemu-user pthread-attr emulation gap. No known software workaround with plain qemu. Try Pi 5 + `box64` or give up on ARM and run URSim on x86 hardware.
- **First boot hangs >20 min** — SD card is probably too slow for the apt+docker pull. Swap for a better one (A2 rating) or switch to NVMe.
- **`ursim.local` doesn't resolve** — your LAN's router may block mDNS. Find the IP via `nmap -sn 192.168.1.0/24` or your DHCP server's lease table and use that instead.
