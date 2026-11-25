
document.addEventListener("DOMContentLoaded", function () {
    const forms = document.querySelectorAll("[data-acknowledge-form]");

    forms.forEach(function (form) {
        form.addEventListener("submit", function (event) {
            const confirmed = window.confirm(
                "Please confirm that you have received this item."
            );

            if (!confirmed) {
                event.preventDefault();
            }
        });
    });
});
