
document.addEventListener("DOMContentLoaded", function () {
    const forms = document.querySelectorAll("[data-issue-form]");

    forms.forEach(function (form) {
        const itemSelect = form.querySelector("[data-inventory-select]");
        const quantityInput = form.querySelector("[data-issue-quantity]");
        const availabilityMessage = form.querySelector("[data-stock-message]");
        const submitButton = form.querySelector("[data-issue-submit]");

        if (!itemSelect || !quantityInput || !availabilityMessage || !submitButton) {
            return;
        }

        function updateStockMessage() {
            const selectedOption = itemSelect.options[itemSelect.selectedIndex];

            if (!selectedOption || !selectedOption.value) {
                availabilityMessage.textContent =
                    "Select an inventory item to check available stock.";

                availabilityMessage.className = "small text-muted mt-1";
                quantityInput.removeAttribute("max");
                submitButton.disabled = true;
                return;
            }

            const available = Number(selectedOption.dataset.available || 0);
            const quantity = Number(quantityInput.value || 0);

            quantityInput.max = available;

            if (available <= 0) {
                availabilityMessage.textContent =
                    "No available stock for this item.";

                availabilityMessage.className = "small text-danger mt-1";
                submitButton.disabled = true;
                return;
            }

            availabilityMessage.textContent =
                "Available stock: " + available.toFixed(2);

            availabilityMessage.className = "small text-success mt-1";

            if (quantity > available) {
                availabilityMessage.textContent +=
                    " — quantity exceeds available stock.";

                availabilityMessage.className = "small text-danger mt-1";
                submitButton.disabled = true;
                return;
            }

            submitButton.disabled = false;
        }

        itemSelect.addEventListener("change", updateStockMessage);
        quantityInput.addEventListener("input", updateStockMessage);

        form.addEventListener("submit", function (event) {
            const selectedOption = itemSelect.options[itemSelect.selectedIndex];
            const available = Number(selectedOption?.dataset.available || 0);
            const quantity = Number(quantityInput.value || 0);

            if (!selectedOption || !selectedOption.value || quantity <= 0 || quantity > available) {
                event.preventDefault();
                updateStockMessage();
            }
        });

        updateStockMessage();
    });
});
