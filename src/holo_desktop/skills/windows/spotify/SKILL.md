---
name: Spotify
description: Searching, playing, queueing, and managing playlists, library, and device output in the Spotify desktop app on Windows.
publisher: H Company
version: "1.0.0"
source_url: https://support.spotify.com/us/article/keyboard-shortcuts/
license: Vendor docs
icon_url: https://api.iconify.design/logos:spotify-icon.svg
---

Spotify is a three-pane Electron app: a left sidebar with "Your Library" (Playlists, Podcasts, Artists, Albums, Audiobooks) and pinned items at the top, the main pane in the middle showing the selected view (Home, Search results, playlist contents, artist page, etc.), and an optional right "Now Playing" pane with the current track's details, lyrics, queue, and credits. The persistent player bar runs across the bottom with playback controls, track info, queue/device buttons, and the volume slider.

## Shortcuts

Spotify on Windows only honors these while the app window has focus — there are no global media hotkeys built in (the keyboard's dedicated media keys still work). `Ctrl+/` opens the in-app shortcuts overlay, the authoritative reference.

Search and navigation: `Ctrl+K` opens Search (the most-used shortcut by far — type any artist, song, album, podcast, or audiobook). `Ctrl+L` jumps to Search from anywhere; `Alt+Shift+H` jumps to Home; `Alt+Shift+J` jumps to the Now Playing context (the album/playlist that owns the current track). `Ctrl+F` filters the current view. `Alt+J` opens the context menu for the focused item (right-click equivalent — Add to Playlist, Save to Library, Share, View Artist, etc.). `Ctrl+,` opens Preferences.

Library sections: `Alt+Shift+0` Library overview, `Alt+Shift+1` Playlists, `Alt+Shift+2` Podcasts, `Alt+Shift+3` Artists, `Alt+Shift+4` Albums, `Alt+Shift+5` Audiobooks. `Alt+Shift+S` jumps to Liked Songs, `Alt+Shift+M` Made For You, `Alt+Shift+N` New Releases, `Alt+Shift+C` Charts, `Alt+Shift+Q` opens the Queue. `Alt+Shift+L` toggles the Library sidebar, `Alt+Shift+R` toggles the Now Playing sidebar.

Playback: `Space` play/pause. `M` mute/unmute. `Ctrl+S` toggle shuffle, `Ctrl+R` cycle repeat (off → all → one). `Alt+Shift+B` like/unlike the currently-playing song. Next/previous track and volume have no default key combo — use the player-bar buttons and volume slider, or the keyboard's media keys.

Queue and list focus: with a track focused in any list, `Right Arrow` adds it to the Queue, `Left Arrow` adds it to the Library (Liked Songs for tracks, Saved for albums/podcasts), `Up Arrow` / `Down Arrow` step to the previous/next row.

## Search-first workflow

`Ctrl+K` is the entry point for almost every task. Type the query — Spotify scopes results to Songs, Artists, Albums, Playlists, Podcasts & Shows, Audiobooks, and Profiles in tabs at the top of the results pane. `Tab` switches result categories; `Enter` on a result navigates to it (NOT plays it — playing requires hovering the result and clicking the green play button, or focusing the row and pressing `Enter` on it).

For commands that need a specific track, search for "artist - track name" then play the first result. For commands that need to play an album from start, search "album name" then click the album, then play. For mood/genre/situation playlists, Spotify's curated playlists ("Discover Weekly", "Daily Mix 1", "Release Radar") are reachable via search or under Home → Made For You.

## Playlists

Create with `Ctrl+N`; the new playlist appears in the sidebar with a generic name, ready to rename. Add tracks by dragging from any list, right-clicking → "Add to playlist", or `Alt+J` → "Add to playlist". Reorder by dragging rows within the playlist view; remove with `Delete` on the focused row.

Collaborative playlists (right-click the playlist → "Collaborative playlist") let any invitee add/remove tracks. Useful for shared situations (party playlist, road trip) but means edits are immediate and visible to all collaborators — confirm before mass-editing a collaborative playlist.

## Device output

The Connect icon (looks like a speaker, bottom-right of the player bar) opens the device picker — Spotify can play to this PC, other devices signed into the same account (phone, web player, other computers), or supported smart speakers. Switching device hands off playback mid-song without interruption.

The user's current playback device is shown in green at the bottom of the player bar. If the user says "play X on the speaker", verify which device is selected — playing to the wrong device is annoying but recoverable; playing loudly to the office speaker when the user wanted private playback is socially expensive.

## The play and like boundaries

Pressing play on any track or starting a playlist replaces the current playback queue with the new context. This is silent and immediate — no confirmation. If the user has a carefully-curated queue going, starting "Daily Mix 1" wipes it. Use the queue-add (`Right Arrow` on a focused track) to preserve the existing context.

Liking a song (`Alt+Shift+B` or the heart icon) adds it to Liked Songs, which is also a Smart-playlist source feeding Discover Weekly and recommendations. Liking on the user's behalf shapes their future recommendations — only like songs the user has explicitly said they want saved.

## Verification

After playing, the player bar shows the track title, artist, and elapsed time advancing. After search, the result pane updates with categorized tabs. After adding to playlist, the playlist's track count in the sidebar increments. If playback doesn't start: a wrong device may be selected (check Connect), the user's session may have been taken over by another device (Spotify only allows one active stream per Free account), or the track may be unavailable in the user's region.

## Sources

Spotify's official keyboard shortcuts: https://support.spotify.com/us/article/keyboard-shortcuts/. The in-app `Ctrl+/` overlay is the most current reference.
