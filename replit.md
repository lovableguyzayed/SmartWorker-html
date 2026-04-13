# SmartWorker - Employee Management System

## Overview

SmartWorker is a Flask-based employee management web application designed for managing workers, tracking attendance, handling payroll, and generating employee ID cards. The system is built with a focus on daily wage workers and provides comprehensive tools for HR management and workforce tracking.

## System Architecture

### Backend Framework
- **Flask**: Core web framework handling HTTP requests and routing
- **SQLAlchemy**: ORM for database operations with declarative base model
- **Flask-Login**: User session management and authentication
- **Werkzeug**: Security utilities for password hashing and proxy handling

### Frontend Technology Stack
- **Tailwind CSS**: Utility-first CSS framework for responsive UI design
- **Font Awesome**: Icon library for consistent visual elements
- **Inter Font**: Modern typography from Google Fonts
- **HTML5 Templates**: Jinja2 templating with modular base template structure

### Database Architecture
- **SQLite**: Default development database (fallback)
- **PostgreSQL**: Production database support via psycopg2-binary
- **Flexible Configuration**: Environment-based database URL configuration

## Key Components

### 1. User Management System
- **Authentication**: Username/password login with secure password hashing
- **User Roles**: Admin and manager role-based access control
- **Session Management**: Persistent login sessions with Flask-Login

### 2. Worker Profile Management
- **Comprehensive Profiles**: Full employee information storage
- **Multiple Payment Types**: Daily, monthly, hourly, and project-based compensation
- **Employee Classification**: Support for various employee types (Daily Wage, Full Time, etc.)
- **Department Organization**: Departmental grouping and filtering

### 3. Attendance Tracking System
- **Daily Attendance**: Date-based attendance recording
- **Multiple Status Types**: Present, absent, late, leave tracking
- **Calendar Integration**: Calendar view for attendance visualization
- **Bulk Operations**: Mass attendance management capabilities

### 4. Digital ID Card Generation
- **QR Code Integration**: Employee identification with QR codes
- **PDF Export**: Printable ID card generation using jsPDF and html2canvas
- **Professional Design**: Branded ID cards with company information

### 5. Payroll Management
- **Flexible Pay Structures**: Support for various compensation models
- **Overtime Calculation**: Configurable overtime rates and tracking
- **Working Hours Management**: Start/end time tracking with break duration

## Data Flow

### 1. User Authentication Flow
1. User submits login credentials
2. System validates against hashed passwords in database
3. Flask-Login creates secure session
4. User redirected to dashboard with role-based access

### 2. Worker Management Flow
1. Admin creates/edits worker profiles
2. System generates unique worker IDs
3. Profile data stored with comprehensive details
4. QR codes generated for identification

### 3. Attendance Processing Flow
1. Daily attendance data collection
2. Status recording (present/absent/late/leave)
3. Calendar visualization and reporting
4. Bulk operations for efficiency

### 4. ID Card Generation Flow
1. Worker profile data retrieval
2. Dynamic HTML/CSS card generation
3. Client-side rendering with html2canvas
4. PDF generation using jsPDF library

## External Dependencies

### Core Framework Dependencies
- **Flask 3.1.1**: Web application framework
- **SQLAlchemy 2.0.41**: Database ORM
- **Gunicorn 23.0.0**: WSGI HTTP server for production

### Authentication & Security
- **Flask-Login 0.6.3**: User session management
- **Werkzeug 3.1.3**: Security utilities
- **PyJWT 2.10.1**: JSON Web Token handling
- **OAuthLib 3.3.0**: OAuth authentication support

### Database & Data Processing
- **psycopg2-binary 2.9.10**: PostgreSQL adapter
- **Flask-SQLAlchemy 3.1.1**: Flask-SQLAlchemy integration

### UI & Document Generation
- **QRCode 8.2**: QR code generation
- **Pillow 11.2.1**: Image processing for QR codes
- **Email-Validator 2.2.0**: Email validation utilities

### Optional Integrations
- **Flask-Dance 7.1.0**: OAuth provider integration (future use)

## Deployment Strategy

### Development Environment
- **Local Development**: SQLite database for rapid prototyping
- **Debug Mode**: Enabled via Flask development server
- **Hot Reload**: Automatic server restart on file changes

### Production Environment
- **Gunicorn WSGI Server**: Production-ready HTTP server
- **PostgreSQL Database**: Scalable production database
- **Environment Configuration**: DATABASE_URL and SESSION_SECRET via environment variables
- **Autoscale Deployment**: Configured for Replit's autoscale deployment target

### Database Configuration
- **Connection Pooling**: Pool recycle every 300 seconds
- **Health Checks**: Pool pre-ping enabled for connection validation
- **Flexible Schema**: Automatic table creation on application startup

### Security Considerations
- **Password Hashing**: Werkzeug secure password hashing
- **Session Security**: Configurable session secret key
- **Proxy Headers**: ProxyFix middleware for reverse proxy deployments

## Changelog
- June 18, 2025. Initial setup

## User Preferences

Preferred communication style: Simple, everyday language.