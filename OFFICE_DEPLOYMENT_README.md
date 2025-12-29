# 🚀 Attendance Tracker - Office Network Deployment

This guide helps you run the Attendance Tracker application on your office network so all devices can access it.

## 📋 Prerequisites

- Python 3.8+ installed on the server machine
- All office devices on the same network (WiFi/LAN)
- Project files copied to the server machine

## 🖥️ Quick Start (Server Machine)

### Method 1: One-Click Script (Recommended)
```bash
# Double-click this file or run in terminal:
./run_server.sh
```

### Method 2: Manual Start
```bash
cd /path/to/attendance_system
python3 manage.py runserver 0.0.0.0:8000
```

## 🌐 Access from Other Devices

### Step 1: Find Server IP Address

#### Quick Method (Recommended):
```bash
# macOS/Linux:
./find_ip.sh

# Windows (double-click or run):
find_ip.bat
```

#### Manual Method:
```bash
# macOS/Linux
hostname -I | awk '{print $1}'

# Windows (Command Prompt)
ipconfig | findstr /i "ipv4"
```

Example output: `192.168.1.100`

### Step 2: Access from Any Office Device
Open browser and go to:
```
http://[SERVER_IP]:8000
```

For example:
```
http://192.168.1.100:8000
```

## 🔧 Network Configuration

### Firewall Settings (macOS)
1. System Settings → Network → Firewall
2. Turn off firewall temporarily OR allow Python

### Windows Firewall
1. Windows Security → Firewall & network protection
2. Allow app through firewall → Python

### Router Settings (if needed)
- Ensure all devices are on the same network
- Check if guest network isolation is disabled

## 👥 User Access

### Admin Access
- **Username:** admin (or your admin username)
- **Password:** your admin password
- Full access to all features

### Employee Access
- **Username:** employee ID
- **Password:** employee's password
- Limited to personal attendance features

## 🛠️ Troubleshooting

### Can't Connect from Other Devices?
1. **Check IP Address:** Run `hostname -I` on server
2. **Firewall:** Disable firewall temporarily
3. **Network:** Ensure all devices on same WiFi network
4. **Port:** Make sure port 8000 isn't blocked

### Server Not Starting?
1. **Dependencies:** Run `pip install -r requirements.txt`
2. **Database:** Run `python3 manage.py migrate`
3. **Port Conflict:** Try different port: `python3 manage.py runserver 0.0.0.0:8080`

### Database Issues?
```bash
# Reset database
python3 manage.py flush
python3 manage.py migrate
python3 manage.py createsuperuser
```

## 🔒 Security Notes

⚠️ **Development Server Warning:**
- This setup uses Django's development server
- Not suitable for production use
- For production, use proper web server (Apache/Nginx + Gunicorn)

### Office Network Security:
- Use strong passwords
- Regularly backup database
- Monitor server access logs
- Consider VPN for remote access

## 📱 Mobile Access

The application works on:
- ✅ Desktop browsers (Chrome, Firefox, Safari, Edge)
- ✅ Tablets
- ✅ Mobile phones (responsive design)
- ✅ All major operating systems

## 🆘 Support

If you encounter issues:
1. Check server console for error messages
2. Verify network connectivity
3. Ensure all devices can ping the server IP
4. Check firewall settings

---

**Happy Tracking! 🎯**

*Generated for Attendance Tracker v2.0*
