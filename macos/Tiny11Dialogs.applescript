on run argv
	set action to item 1 of argv
	try
		if action is "choose-iso" then
			set selectedFile to choose file with prompt "Choose the original Windows 11 x64 ISO" of type {"public.iso-image"}
			return POSIX path of selectedFile
		else if action is "choose-folder" then
			set selectedFolder to choose folder with prompt "Choose where the installer and USB files should be saved" default location (path to downloads folder)
			return POSIX path of selectedFolder
		else if action is "choose-edition" then
			set choices to {}
			repeat with i from 2 to count of argv
				set end of choices to item i of argv
			end repeat
			set selectedItems to choose from list choices with title "Choose the Windows edition" with prompt "Select the edition covered by your Windows license." OK button name "Continue" cancel button name "Cancel" default items {item 1 of choices}
			if selectedItems is false then return "__CANCELLED__"
			return item 1 of selectedItems
		else if action is "confirm-dependencies" then
			set promptText to item 2 of argv
			set choice to button returned of (display dialog promptText with title "Install Mac tools" buttons {"Cancel", "Install"} default button "Install" cancel button "Cancel")
			return choice
		else if action is "notice" then
			set titleText to item 2 of argv
			set bodyText to item 3 of argv
			display dialog bodyText with title titleText buttons {"OK"} default button "OK"
			return "OK"
		end if
		return ""
	on error errorText number errorNumber
		if errorNumber is -128 then return "__CANCELLED__"
		error errorText number errorNumber
	end try
end run
