function updateStatus(message) {
    const statusElement = document.getElementById("status");
    if (statusElement) {
        statusElement.textContent = message;
    }
}

function getLocation() {
    if (!navigator.geolocation) {
        updateStatus("Geolocation is not supported by this browser.");
        return;
    }

    navigator.geolocation.getCurrentPosition(
        function (pos) {
            document.getElementById("lat").value = pos.coords.latitude;
            document.getElementById("lon").value = pos.coords.longitude;
            updateStatus("Location ready.");
        },
        function () {
            updateStatus("Unable to retrieve location.");
        }
    );
}

function useWifi() {
    const wifi = "Office_WiFi";
    updateStatus("Using WiFi...");
    sendData("wifi", wifi);
}

function useLocation() {
    const lat = document.getElementById("lat").value;
    const lon = document.getElementById("lon").value;

    if (!lat || !lon) {
        updateStatus("Location not ready yet. Allow location access and try again.");
        getLocation();
        return;
    }

    updateStatus("Using Location...");
    sendData("location", lat + "," + lon);
}

function sendData(type, value) {
    const staffId = document.getElementById("staff_id").value;

    fetch("/attendance/", {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": getToken("csrftoken")
        },
        body: JSON.stringify({
            staff_id: staffId,
            type: type,
            value: value
        })
    })
        .then(res => res.json())
        .then(data => {
            const result = document.getElementById("result");
            if (data.error) {
                updateStatus(data.error);
                result.innerHTML = "";
                return;
            }

            updateStatus("Attendance recorded.");
            result.innerHTML = "Status: " + data.status + "<br>Time: " + data.time;
        })
        .catch(() => {
            updateStatus("Attendance request failed.");
        });
}

function getToken(name) {
    const cookies = document.cookie ? document.cookie.split(";") : [];

    for (let i = 0; i < cookies.length; i += 1) {
        const cookie = cookies[i].trim();
        if (cookie.startsWith(name + "=")) {
            return decodeURIComponent(cookie.substring(name.length + 1));
        }
    }

    return "";
}

document.addEventListener("DOMContentLoaded", function () {
    if (document.getElementById("lat") && document.getElementById("lon")) {
        getLocation();
    }
});
