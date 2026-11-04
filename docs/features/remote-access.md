# Remote access

Use the web UI from your phone or another computer over Tailscale, and optionally have it start on demand.

## Using it

`desktop/start_agent_ui.fish` keeps uvicorn on `127.0.0.1:8000`. If `tailscale` is installed, it also runs `tailscale serve --bg 8000` to publish the UI on your tailnet at `https://<machine>.<tailnet>.ts.net`. The mic button on other devices needs this HTTPS address.

One-time setup on CachyOS/Arch:

```
sudo pacman -S tailscale
sudo systemctl enable --now tailscaled
sudo tailscale up                       # log in via the printed URL
sudo tailscale set --operator=$USER     # lets the launcher run `tailscale serve` without sudo
```

Then turn on MagicDNS and HTTPS certificates under DNS in the Tailscale admin console. `tailscale serve` gives you a link to do this if they're off. Only devices on your tailnet can reach the URL, and the app's own login still applies. `tailscale serve reset` stops publishing it.

## Starting on demand

To start the UI from another device just by opening the URL, install the systemd user units in `desktop/`:

```
systemctl --user link $PWD/desktop/agent0-ui.service $PWD/desktop/agent0-ui-proxy.service $PWD/desktop/agent0-ui-proxy.socket
systemctl --user enable --now agent0-ui-proxy.socket
sudo loginctl enable-linger $USER        # listen even when you're logged out / after reboot
tailscale serve --bg 8000                # once; the serve config persists
journalctl --user -u agent0-ui -f        # logs
```

A socket listens on port 8000. The first request starts uvicorn on port 8001, behind a proxy, which takes a few seconds. With the socket enabled, the desktop launcher starts the app through it and follows these logs instead of running its own uvicorn. To turn on-demand starting off, run `systemctl --user disable --now agent0-ui-proxy.socket`.

## Limits

- The app stops after 30 minutes without connections and loses its in-memory state: parked approvals and the "play number N" list.
