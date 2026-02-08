# Features
- [x] #1 Favorite location feature
    - having a list of saved locations to quickly jump to
    - the location simply save with txt, and load from txt file. Format is latitude,longitude,name (name is optional). each line is one location.
    - if the txt file is not found, create an empty one on app startup.
    - option to import favorite locations from txt file
    - option to save current location as favorite
    - option to delete favorite locations
    - option to rename favorite locations
    - manage favorite locations in a separate popup window
    - auto-naming with reverse geocoding (Country / City / District format) using system locale
- [x] #2 Pause/resume on Cruise mode (blocked by #Bugs2)
    - a button to pause/resume the cruise mode without clearing the target location
    - see CruiseModeRefactor.md for more details
- [x] #3 Last Location on app restart (related to #7)
    - save the last set location to a file on app exit
    - load the last set location from the file on app startup
    - if the file is not found, start with default location
- [ ] #4 Search bar on map to jump to location
    - a search bar on top of the map to input city name, address or some keywords to search location
    - use some free geocoding API to get the location from the keywords
- [x] #5 Unlock the speed limit with configurable max value
    - option to set custom speed limit, a check box above current speed slider to enable/disable it, when enabled, and a number input next to check box to set the custom max speed limit value of the slider
- [x] #6 Debug page can set backend address and port
    - in debug page, add input fields to set backend address and port, so user can connect to remote backend server
- [x] #7 memory last position by device in backend (related to #8)
- [x] #8 multi-device support
    - Backend remove selected device logic.
    - let frontend handle device selection, and send device id to backend when setting location eachtime.
- [ ] #9 Save route

# Bugs
- [x] Cruise mode not cleaning target icon on map when reaching destination
- [x] Favorite Location reverse geocoding fail
    - the reverse geocoding fail to get the address, need to investigate and fix it
    - Fixed: Added https://nominatim.openstreetmap.org to CSP connect-src in index.html
- [x] Browser mode, Cruise mode will stop working after tab is inactive for a while
    - see CruiseModeRefactor.md for more details
- [x] Swtich to debug tab and back to Simumlator tap, the map will lost the current location centering and the icons
    - Fixed: Use CSS display to hide/show tabs instead of conditional rendering, so map instance stays mounted
- [ ] Location refresh continues after tunnel stop
    - When stopTunnel is called, LocationService's refresh task continues running
    - main.py _stop_tunnel() only calls tunnel.stop_tunnel() but not location.close_connection()
    - The refresh task keeps trying to send location updates every 3 seconds even though tunnel is gone
    - Fix: Call location.close_connection(udid) when stopping tunnel

# UI Improvements
- [x] Make latitude/longitude text not split line when the number of digits change longer

# Enhancements
- [x] Favorite location
    - Pane the map to the selected favorite location when clicked in the list
    - Can save selected location, not only current location
- [ ] restore existing device location setting from backend when frontend refreshed
    - when frontend start, if the selected device has existing location setting in backend (refreshing), load and set the location on map
- [ ] Simplify tunnel management UX
    - Remove separate "Start Tunnel" button
    - Auto-start tunnel when device is selected (if device requires tunnel for iOS 17+)
    - Add "X" button on connected device label to stop tunnel/disconnect
    - User only needs to select device - tunnel management happens automatically

# Debug features
- [x] Add a dynamic port forwarding debug feature, user can forward frontend, backend 127.0.0.1:port to another network interface addr:port for remote debug. like ngrok, but simpler.