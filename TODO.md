# Features
- [x] Favorite location feature
    - having a list of saved locations to quickly jump to
    - the location simply save with txt, and load from txt file. Format is latitude,longitude,name (name is optional). each line is one location.
    - if the txt file is not found, create an empty one on app startup.
    - option to import favorite locations from txt file
    - option to save current location as favorite
    - option to delete favorite locations
    - option to rename favorite locations
    - manage favorite locations in a separate popup window
    - auto-naming with reverse geocoding (Country / City / District format) using system locale
- [ ] Pause/resume on Cruise mode
    - a button to pause/resume the cruise mode without clearing the target location
- [ ] Keep refresh location
    - a checkbox to enable/disable keep sending set location request even when not moving
    - need to add slice location jittering when enabled
    - refresh interval can be set by user, default to 5 seconds
- [ ] Last Location on app restart
    - save the last set location to a file on app exit
    - load the last set location from the file on app startup
    - if the file is not found, start with default location
- [ ] Search bar on map to jump to location
    - a search bar on top of the map to input city name, address or some keywords to search location
    - use some free geocoding API to get the location from the keywords
- [ ] Unlock the speed limit with configurable max value
    - option to set custom speed limit, a check box above current speed slider to enable/disable it, when enabled, and a number input next to check box to set the custom max speed limit value of the slider

# Bugs
- [x] Cruise mode not cleaning target icon on map when reaching destination

# UI Improvements
- [x] Make latitude/longitude text not split line when the number of digits change longer
