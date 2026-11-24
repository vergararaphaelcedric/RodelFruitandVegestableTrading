
document.addEventListener("DOMContentLoaded", function () {
    // Initialize Bootstrap tooltips.
    document.querySelectorAll('[data-bs-toggle="tooltip"]').forEach(function (element) {
        new bootstrap.Tooltip(element);
    });

    // Automatically dismiss success messages.
    document.querySelectorAll(".alert-success").forEach(function (alert) {
        setTimeout(function () {
            if (bootstrap.Alert.getInstance(alert)) {
                bootstrap.Alert.getInstance(alert).close();
            }
        }, 5000);
    });

    // Prevent accidental double form submissions.
    document.querySelectorAll("form[data-once]").forEach(function (form) {
        form.addEventListener("submit", function () {
            const submitButton = form.querySelector('[type="submit"]');

            if (submitButton) {
                submitButton.disabled = true;
                submitButton.dataset.originalText = submitButton.innerHTML;
                submitButton.innerHTML = "Please wait...";
            }
        });
    });
});
