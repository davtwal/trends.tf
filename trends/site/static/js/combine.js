// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (C) 2021 Sean Anderson <seanga2@gmail.com>

var checkboxes;

function update_checkboxes() {
	let checked = 0;
	for (let checkbox of checkboxes) {
		if (checkbox.checked) {
			checked++;
		}
	}

	if (checked >= 10) {
		for (let checkbox of checkboxes) {
			if (!checkbox.checked) {
				checkbox.disabled = true;
			}
		}
	} else {
		for (let checkbox of checkboxes) {
			if (!checkbox.checked) {
				checkbox.disabled = false;
			}
		}
	}
}

document.addEventListener('DOMContentLoaded', () => {
	checkboxes = document.querySelectorAll("input[form=combine]");
	for (let checkbox of checkboxes) {
		checkbox.addEventListener('change', update_checkboxes);
	}
	update_checkboxes();
});
