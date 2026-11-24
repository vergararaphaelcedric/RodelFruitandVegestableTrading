
document.addEventListener("DOMContentLoaded", function () {
    const formList = document.getElementById("item-form-list");
    const addButton = document.getElementById("add-item");
    const template = document.getElementById("empty-form-template");
    const totalForms = document.getElementById("id_items-TOTAL_FORMS");

    if (!formList || !addButton || !template || !totalForms) {
        return;
    }

    function updateItemNumbers() {
        const rows = formList.querySelectorAll(".item-row");

        rows.forEach((row, index) => {
            const number = row.querySelector(".item-number");

            if (number) {
                number.textContent = index + 1;
            }
        });
    }

    addButton.addEventListener("click", function () {
        const currentCount = Number(totalForms.value);

        if (currentCount >= 30) {
            alert("You can add a maximum of 30 items.");
            return;
        }

        const html = template.innerHTML.replace(
            /__prefix__/g,
            currentCount
        );

        formList.insertAdjacentHTML("beforeend", html);

        totalForms.value = currentCount + 1;

        updateItemNumbers();
    });

    formList.addEventListener("change", function (event) {
        if (event.target.name && event.target.name.endsWith("-DELETE")) {
            const row = event.target.closest(".item-row");

            if (row) {
                row.style.opacity = event.target.checked ? "0.5" : "1";
            }
        }
    });

    updateItemNumbers();
});
