module.exports.Config = {
    NODE_ENV: process.env.NODE_ENV || 'development',
    PORT: process.env.PORT || 3331,
    HOST: process.env.HOST || '0.0.0.0',
    DB_HOST: process.env.DB_HOST || 'localhost',
    DB_PORT: Number(process.env.DB_PORT || 3306),
    DB_USER: process.env.DB_USER || 'root',
    DB_PASS: process.env.DB_PASS || '',
    DB_DATABASE: process.env.DB_DATABASE || 'test',
    SECRET_JWT: process.env.SECRET_JWT || "",
    SENDGRID_API_KEY: process.env.SENDGRID_API_KEY || "SENDGRID_API_KEY",
    SENDGRID_SENDER: process.env.SENDGRID_SENDER || "FROM_EMAIL"
};
