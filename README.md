# simpleDashProxy

A very simple Dash proxy written in Python3

This service acts as a proxy with cache except when it encounters an mpd file.

When an dash mpd file is encaountered it spawns a new process that uses dash-proxy module to download the hole dash in the background.
It still serves request in the meanwhile.
If another mpd file is encounter the current download is stopped an the new is started.

The purpose of this is to be able to cache dash streams in a household where several devices may consume the dash.

This also resolves an issue with Kodi and current inputstream adaptive implementation where you cannot control the buffer.

The current limit of only 1 active download is to avoid spawning many simultanious downloaders just by start watching a few seconds from stream and thus making mathers worse from a standpoing of bandwidth.
