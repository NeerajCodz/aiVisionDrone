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

            // Add Default "None" option
            const defaultOption = document.createElement('option');
            defaultOption.value = "";
            defaultOption.textContent = "Select a Model...";
            defaultOption.selected = true;
            defaultOption.disabled = true; // Act as a placeholder
            modelSelect.appendChild(defaultOption);

            models.forEach(model => {
                const option = document.createElement('option');
                option.value = model.id;
                // Format: TITLE (model-id)
                option.textContent = `${model.name || model.id} (${model.id})`;
                if (model.description) {
                    option.title = model.description;
                }
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

                // If we have significantly fewer logs than before, the server might have restarted or cleared logs.
                // In that case, we should clear our local display.
                // However, for now, let's just assume appending new ones.

                // Sort logs by timestamp just in case
                // logs.sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));

                let newLogsCount = 0;

                logs.forEach(log => {
                    // Create a unique signature for the log to dedup
                    const signature = `${log.timestamp}-${log.source}-${log.message}`;
                    if (!knownLogSignatures.has(signature)) {
                        addLogEntry(log.source, log.message, log.level, log.timestamp);
                        knownLogSignatures.add(signature);
                        newLogsCount++;
                    }
                });

                // Prune knownLogSignatures if it gets too big (optional memory management)
                if (knownLogSignatures.size > 2000) {
                    knownLogSignatures.clear();
                    // This might cause re-rendering execution if we don't clear DOM, but usually server keeps last 100. 
                    // So actually, we should align with server.
                    // A simple way is: if server logs != what we have, sync. 
                    // But appending is safer for "streaming" feel.
                }

            } else {
                setStatus(false);
            }
        } catch (error) {
            // console.error(error); // silent fail
            setStatus(false);
        }
    }

    // Initial Load
    fetchModels();

    // Interval
    setInterval(pollLogs, 1000);

});
