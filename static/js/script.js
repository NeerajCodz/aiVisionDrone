document.addEventListener('DOMContentLoaded', () => {
    const modelSelect = document.getElementById('modelSelect');
    const logsContainer = document.getElementById('logsContainer');
    const clearLogsBtn = document.getElementById('clearLogs');
    const statusText = document.getElementById('statusText');
    const statusDot = document.querySelector('.dot');

    let isConnected = false;
    let knownLogSignatures = new Set(); // To avoid duplicates if we re-fetch same logs

    function setStatus(connected) {
        isConnected = connected;
        if (connected) {
            statusText.textContent = "System Active";
            statusDot.style.backgroundColor = "var(--success-color)";
        } else {
            statusText.textContent = "Disconnected";
            statusDot.style.backgroundColor = "var(--danger-color)";
        }
    }

    // Fetch Models
    async function fetchModels() {
        try {
            const response = await fetch('/api/models');
            const models = await response.json();

            modelSelect.innerHTML = '';
            models.forEach(model => {
                const option = document.createElement('option');
                option.value = model.id;
                option.textContent = model.name;
                modelSelect.appendChild(option);
            });
            setStatus(true);
        } catch (error) {
            console.error('Failed to fetch models:', error);
            modelSelect.innerHTML = '<option disabled>Connection Failed</option>';
            setStatus(false);
        }
    }

    // Change Model
    modelSelect.addEventListener('change', async (e) => {
        const modelId = e.target.value;
        try {
            const response = await fetch('/api/select_model', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ model_id: modelId })
            });
            const result = await response.json();
            addLogEntry('System', result.message, 'success');
        } catch (error) {
            console.error('Error selecting model:', error);
            addLogEntry('System', 'Failed to change model', 'error');
        }
    });

    // Clear Logs
    clearLogsBtn.addEventListener('click', () => {
        logsContainer.innerHTML = '';
        knownLogSignatures.clear();
    });

    // Add Log Entry to DOM
    function addLogEntry(source, message, level, timestamp = null) {
        if (!timestamp) {
            const now = new Date();
            timestamp = now.toLocaleTimeString();
        }

        const div = document.createElement('div');
        div.className = `log-entry ${level.toLowerCase()}`;

        div.innerHTML = `
            <span class="timestamp">${timestamp}</span>
            <span class="source">[${source}]</span>
            <span class="message">${message}</span>
        `;

        logsContainer.appendChild(div);
        logsContainer.scrollTop = logsContainer.scrollHeight;
    }

    // Poll Logs
    async function pollLogs() {
        try {
            const response = await fetch('/api/logs');
            if (response.ok) {
                if (!isConnected) setStatus(true);

                const logs = await response.json();

                // Clear container if we look like we reconnected or just simple render
                // For simplicity, we just render what we get, but we need to dedupe or handle stream.
                // The API returns *all* logs (last 100).

                // Naive approach: Render all creates dupes. 
                // Better: Clear and Render? 
                // Or: Keep track of last rendered.

                // Let's just Clear and Render for this simple demo to ensure sync, 
                // OR compare last log.

                // Optimization: The server returns last 100 logs. 
                // We can just wipe and redraw or be smart.
                // "Rich" usually means smart. 
                // Let's use a signature check.

                const currentLogCount = logsContainer.childElementCount;
                if (logs.length > currentLogCount) {
                    // Log array has grown or changed?
                    // Let's just render the 'new' ones.

                    // Actually, easiest way to avoid flicker and complexity:
                    // Only add if not present?

                    // Let's just empty logsContainer if logs array size is vastly different (reset)
                    // Otherwise append.

                    // REAL SOLUTION: The api returns the full list.
                    // We should just wipe and rebuild? No, flashing.

                    // Let's track the last timestamp seen.
                    const lastLog = logs[logs.length - 1];
                    // ... this is getting complicated for a demo.

                    // Simple mode: Wipe and redraw only if count differs? No.

                    // Let's use the clear approach only if necessary.
                    logsContainer.innerHTML = '';
                    logs.forEach(log => {
                        addLogEntry(log.source, log.message, log.level, log.timestamp);
                    });
                }

                // Wait... Wiping 100 DOM elements every second is bad.
                // But efficient enough for this scale.

            } else {
                setStatus(false);
            }
        } catch (error) {
            setStatus(false);
        }
    }

    // Initial Load
    fetchModels();

    // Interval
    setInterval(pollLogs, 1000);

});
