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
    - backend sse need to send device id with each location update event
    - frontend need to save location info per device, when switching device, load the last location set for that device
    - frontend during select device change, load the infos from backend. The info should have:
      - current location when backend have refreshing task running for the device
      - last location if backend not refreshing
      - if is cruising
        - cruising target location
      - if is route cruising
        - show the route relate info on map
    
- [ ] #9 Favorite route feature
    - Save the current view of route (waypoints and order).
    - Load the route back to map. ( after load user can decide how to go to start point, directly jump / strate line cruise / pathfinding route cruise)
    - default name is "country / city / district (start point) -> [country / city / district] (start point)" format, skip the end point name if same as start point, use reverse geocoding with system locale. 
    - Manage favorite routes in a separate popup window, similar to favorite location management.
    - 


# Bugs
- [x] Cruise mode not cleaning target icon on map when reaching destination
- [x] Favorite Location reverse geocoding fail
    - the reverse geocoding fail to get the address, need to investigate and fix it
    - Fixed: Added https://nominatim.openstreetmap.org to CSP connect-src in index.html
- [x] Browser mode, Cruise mode will stop working after tab is inactive for a while
    - see CruiseModeRefactor.md for more details
- [x] Swtich to debug tab and back to Simumlator tap, the map will lost the current location centering and the icons
    - Fixed: Use CSS display to hide/show tabs instead of conditional rendering, so map instance stays mounted
- [ ] Switch to debug tab and back to simulator tab, the map can not display normally, it will be blank and only showing top-left corner of the map, need to refresh the page to make it work again.
- [x] Page will become laggy due to many debug log in debug page
    - The debug log only keep 100 lines by default, user can change the log limit in a input box, next to the log clear button, to avoid too many logs cause the page laggy. When the log limit is reached, the oldest log will be removed when new log comes in.
- [ ] idle location refreshing will not retry with getting new tunnel if refresh failed due to connection issue.
    - When the location refresh task encounters a connection error (e.g., tunnel down), it should trigger a retry mechanism that attempts to get a new tunnel and resend the location update. This ensures that transient connection issues don't cause the location updates to stop indefinitely.
    - The low-level location setting should be unified accross every place in the codebase, so that any location update will have the retry logic built in. This includes both the periodic refresh task and any on-demand location updates triggered by user actions. This could need a refactor task for better resolve.
- [ ] multi-device support
    - The frontend auto-mode switch by device state is not fully correct.  When I'm in idle device on direct mode, switch back to a device is route cruising, the route cruise panel showing, but the mode still select the direct mode and cause the cruise pause. The correct behavior should be switch to route mode when switch to a device with route cruise state, no matter what the previous mode is.
    - The speed slider does not change to device speed when switch device, test in two device in route cruise mode with different speed, switch between them, the speed slider does not update to the current device speed, it always keep the previous device speed. The correct behavior should be update the speed slider to current device speed when switch device.
# UI Improvements
- [x] Make latitude/longitude text not split line when the number of digits change longer

# Enhancements
- [x] Favorite location
    - Pane the map to the selected favorite location when clicked in the list
    - Can save selected location, not only current location
- [ ] restore existing device location setting from backend when frontend refreshed
    - when frontend start, if the selected device has existing location setting in backend (refreshing), load and set the location on map
    - should be done with feature #8 multi-device support, since we need to save location per device in backend
- [x] Simplify tunnel management UX
    -  When backend start up, check if tunneld if running by http query. if not, run tunneld command directly. From user perspective, they will see a admimn prompt showing when project start up if tunneld not running.  
    - Remove separate "Start Tunnel" button
    - Auto-start tunnel when device is selected (if device requires tunnel for iOS 17+)
    - Add "X" button on connected device label to stop tunnel(disconnect)
    - User only needs to select device - tunnel management happens automatically
- [ ] can not undo last waypoint in route cruise mode running
- [ ] Route cruise can go reverse


# Debug 
- [x] Add a dynamic port forwarding debug feature, user can forward frontend, backend 127.0.0.1:port to another network interface addr:port for remote debug. like ngrok, but simpler.