FROM node:18-alpine AS build

WORKDIR /app

COPY package*.json ./

RUN npm install

COPY public/ public/
COPY src/ src/

RUN npm run build

FROM nginx:1.25-alpine

COPY --from=build /app/build /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 8080

CMD ["nginx", "-g", "daemon off;"]