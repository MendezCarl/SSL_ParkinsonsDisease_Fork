FROM node:alpine

WORKDIR /app

COPY package*.json ./

RUN npm install

COPY . .

# In Docker the backend service is reachable at http://backend:8000
ENV BACKEND_ORIGIN=http://backend:8000

EXPOSE 5174

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
