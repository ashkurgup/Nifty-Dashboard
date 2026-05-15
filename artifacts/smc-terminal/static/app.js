// static/app.js
console.log("app.js loaded successfully");

document.addEventListener("DOMContentLoaded", () => {
    const priceEl = document.getElementById("niftyPrice");
    const statusEl = document.getElementById("marketStatus");

    if (priceEl) {
        priceEl.textContent = "22,450.00";
    }

    if (statusEl) {
        statusEl.textContent = "● LIVE";
        statusEl.style.color = "#16a34a";
    }
});
