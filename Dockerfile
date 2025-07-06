# Use an official Python runtime as a parent image
# Using a specific version and the 'slim' variant for a smaller image size
FROM python:3.11

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
# --no-cache-dir reduces image size
# --upgrade pip ensures we have the latest pip
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application files into the container
# This includes app.py and the 'gems' folder
COPY . .

# Expose the port Streamlit runs on
EXPOSE 8501

# The command to run the app when the container launches
# --server.address=0.0.0.0 is crucial to allow connections from outside the container
# --server.port=8501 is explicit and good practice
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
# CMD ["streamlit", "run", "app.py", "--server.port=8501"]