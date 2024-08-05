document.addEventListener('DOMContentLoaded', () => {
    const logsContainer = document.getElementById('logs-container');
    const crmContainer = document.getElementById('crm-container');
    const eventSource = new EventSource('/api/campaign-status');

    eventSource.onmessage = function(event) {
        console.log('Received event:', event.data);
        const data = JSON.parse(event.data);
        const logEntry = document.createElement('p');

        switch(data.type) {
            case 'log':
                logEntry.textContent = data.message;
                logsContainer.appendChild(logEntry);
                logsContainer.scrollTop = logsContainer.scrollHeight;
                break;
            case 'status':
                logEntry.textContent = data.message;
                logEntry.style.fontWeight = 'bold';
                logsContainer.appendChild(logEntry);
                logsContainer.scrollTop = logsContainer.scrollHeight;
                if (data.message === 'Campaign finished') {å
                    eventSource.close();
                }
                break;
            case 'error':
                logEntry.textContent = 'Error: ' + data.message;
                logEntry.style.color = 'red';
                logsContainer.appendChild(logEntry);
                logsContainer.scrollTop = logsContainer.scrollHeight;
                break;
            case 'crm':
                updateCRM(data.message);
                break;
        }
    };

    eventSource.onerror = function(error) {
        console.error('EventSource failed:', error);
        eventSource.close();
    };

    function updateCRM(crmData) {
        crmContainer.innerHTML = ''; // Clear existing data
        const table = document.createElement('table');
        const headers = Object.keys(crmData[0]);

        // Create table header
        const headerRow = document.createElement('tr');
        headers.forEach(header => {
            const th = document.createElement('th');
            th.textContent = header;
            headerRow.appendChild(th);
        });
        table.appendChild(headerRow);

        // Create table rows
        crmData.forEach(lead => {
            const row = document.createElement('tr');
            headers.forEach(header => {
                const td = document.createElement('td');
                td.textContent = lead[header];
                row.appendChild(td);
            });
            table.appendChild(row);
        });

        crmContainer.appendChild(table);
    }
});