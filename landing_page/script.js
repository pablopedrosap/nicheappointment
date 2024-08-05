document.addEventListener('DOMContentLoaded', () => {
    const formStep1 = document.getElementById('lead-form-step1');
    const formStep2 = document.getElementById('lead-form-step2');
    const loadingIndicator = document.createElement('div');
    loadingIndicator.id = 'loading-indicator';
    loadingIndicator.innerHTML = 'Starting campaign...';
    loadingIndicator.style.display = 'none';
    document.body.appendChild(loadingIndicator);

    formStep1.addEventListener('submit', (e) => {
        e.preventDefault();
        formStep1.style.display = 'none';
        formStep2.style.display = 'flex';
    });

    formStep2.addEventListener('submit', async (e) => {
        e.preventDefault();

        const formData = {
            niche: document.getElementById('niche').value,
            location: document.getElementById('location').value,
            website: document.getElementById('website').value,
            name: document.getElementById('name').value,
            offer: document.getElementById('offer').value,
            gmail: document.getElementById('gmail').value,
            appPassword: document.getElementById('app-password').value
        };

        // Show loading indicator
        loadingIndicator.style.display = 'block';
        formStep2.style.display = 'none';

        try {
            // Send the form data
            const response = await fetch('/api/start-campaign', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(formData),
            });

            if (!response.ok) {
                throw new Error('Failed to start campaign');
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder();

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                const decodedChunk = decoder.decode(value, { stream: true });
                const lines = decodedChunk.split('\n\n');

                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        const data = JSON.parse(line.slice(6));
                        console.log(data);  // Log each message for debugging

                        if (data.type === 'status' && data.message === 'Campaign finished') {
                            window.location.href = '/logs';
                            return;
                        } else if (data.type === 'error') {
                            throw new Error(data.message);
                        } else if (data.type === 'log') {
                            // Update loading indicator with latest log
                            loadingIndicator.innerHTML = `Starting campaign...<br>${data.message}`;
                        }
                    }
                }
            }
        } catch (error) {
            alert('There was an error starting your campaign. Please try again.');
            console.error('Error:', error);
            // Hide loading indicator and show form again on error
            loadingIndicator.style.display = 'none';
            formStep2.style.display = 'flex';
        }
    });
});