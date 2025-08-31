from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_from_directory
import os
import subprocess
import shutil
import tempfile
import zipfile
import base64
import re
import json
import uuid
from datetime import datetime
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'

# Project storage
PROJECTS_FILE = 'projects.json'
if not os.path.exists(PROJECTS_FILE):
    with open(PROJECTS_FILE, 'w') as f:
        json.dump([], f)

def load_projects():
    """Load projects from JSON file"""
    try:
        with open(PROJECTS_FILE, 'r') as f:
            return json.load(f)
    except:
        return []

def save_projects(projects):
    """Save projects to JSON file"""
    with open(PROJECTS_FILE, 'w') as f:
        json.dump(projects, f, indent=2)

def get_project_by_id(project_id):
    """Get project by ID"""
    projects = load_projects()
    for project in projects:
        if project['id'] == project_id:
            return project
    return None

def update_project(project_id, **kwargs):
    """Update project details"""
    projects = load_projects()
    for i, project in enumerate(projects):
        if project['id'] == project_id:
            for key, value in kwargs.items():
                if key in project:
                    project[key] = value
            projects[i] = project
            save_projects(projects)
            return True
    return False

def delete_project(project_id):
    """Delete project and remove directory"""
    project = get_project_by_id(project_id)
    if not project:
        return False
    
    # Remove project directory
    project_path = project['path']
    if os.path.exists(project_path):
        try:
            shutil.rmtree(project_path)
        except:
            pass
    
    # Remove from projects list
    projects = load_projects()
    projects = [p for p in projects if p['id'] != project_id]
    save_projects(projects)
    return True

# Helper functions
def validate_name(name):
    """Validate project/app names for Django compatibility"""
    return name.isidentifier() and not name[0].isdigit()

def get_installed_apps(project_path):
    """Get list of installed apps in the project"""
    settings_path = os.path.join(project_path, os.path.basename(project_path), 'settings.py')
    if not os.path.exists(settings_path):
        return []
    
    with open(settings_path, 'r') as f:
        content = f.read()
    
    # Extract INSTALLED_APPS list
    pattern = r"INSTALLED_APPS\s*=\s*\[(.*?)\]"
    match = re.search(pattern, content, re.DOTALL)
    if not match:
        return []
    
    apps_str = match.group(1)
    apps = []
    for line in apps_str.split('\n'):
        line = line.strip().strip(',').strip("'\"")
        if line and not line.startswith('#') and not line.startswith('django.contrib'):
            apps.append(line)
    
    return apps

def add_app_to_project(project_path, app_name):
    """Add a new app to the project"""
    if not validate_name(app_name):
        raise ValueError(f"Invalid app name: {app_name}")
    
    # Check if app already exists
    if app_name in get_installed_apps(project_path):
        raise ValueError(f"App '{app_name}' already exists")
    
    # Create the app
    manage_py_path = os.path.join(project_path, 'manage.py')
    try:
        subprocess.run(
            ['python', manage_py_path, 'startapp', app_name],
            cwd=project_path,
            check=True,
            capture_output=True
        )
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Error creating app {app_name}: {e.stderr.decode('utf-8')}")
    
    # Update settings.py
    settings_path = os.path.join(project_path, os.path.basename(project_path), 'settings.py')
    with open(settings_path, 'r') as f:
        settings_content = f.read()
    
    # Add app to INSTALLED_APPS
    if f"'{app_name}'" not in settings_content:
        settings_content = settings_content.replace(
            "INSTALLED_APPS = [",
            f"INSTALLED_APPS = [\n    '{app_name}',"
        )
    
    with open(settings_path, 'w') as f:
        f.write(settings_content)
    
    return True

def remove_app_from_project(project_path, app_name):
    """Remove an app from the project"""
    # Check if app exists
    if app_name not in get_installed_apps(project_path):
        raise ValueError(f"App '{app_name}' does not exist")
    
    # Update settings.py
    settings_path = os.path.join(project_path, os.path.basename(project_path), 'settings.py')
    with open(settings_path, 'r') as f:
        settings_content = f.read()
    
    # Remove app from INSTALLED_APPS
    pattern = rf"(\s*)'{re.escape(app_name)}',?"
    settings_content = re.sub(pattern, "", settings_content)
    
    with open(settings_path, 'w') as f:
        f.write(settings_content)
    
    # Remove app directory
    app_path = os.path.join(project_path, app_name)
    if os.path.exists(app_path):
        try:
            shutil.rmtree(app_path)
        except:
            pass
    
    return True

def create_django_project(project_name, project_dir, is_drf=False, apps=None):
    """Create a Django project with optional DRF and apps"""
    if not validate_name(project_name):
        raise ValueError("Invalid project name")
    
    project_path = os.path.join(project_dir, project_name)
    if os.path.exists(project_path):
        raise ValueError("Project already exists")
    
    # Create project directory
    os.makedirs(project_path)
    
    # Create Django project
    try:
        subprocess.run(
            ['django-admin', 'startproject', project_name, project_path],
            check=True,
            capture_output=True
        )
    except subprocess.CalledProcessError as e:
        shutil.rmtree(project_path)
        raise RuntimeError(f"Error creating project: {e.stderr.decode('utf-8')}")
    
    # Add DRF if requested
    if is_drf:
        requirements_path = os.path.join(project_path, 'requirements.txt')
        with open(requirements_path, 'a') as f:
            f.write('djangorestframework\n')
        
        # Update settings.py
        settings_path = os.path.join(project_path, project_name, 'settings.py')
        with open(settings_path, 'r') as f:
            settings_content = f.read()
        
        # Add rest_framework to INSTALLED_APPS
        if "'rest_framework'" not in settings_content:
            settings_content = settings_content.replace(
                "INSTALLED_APPS = [",
                "INSTALLED_APPS = [\n    'rest_framework',"
            )
        
        with open(settings_path, 'w') as f:
            f.write(settings_content)
    
    # Create apps if requested
    if apps:
        for app_name in apps:
            add_app_to_project(project_path, app_name)
    
    return project_path

def get_home_directory():
    """Get the user's home directory"""
    return os.path.expanduser("~")

def list_directory(path):
    """List contents of a directory"""
    try:
        # Normalize the path
        path = os.path.normpath(path)
        
        # Security check - ensure path is within allowed directories
        home_dir = get_home_directory()
        if not os.path.commonpath([path, home_dir]) == home_dir:
            return {"error": "Access denied - path outside home directory"}
        
        if not os.path.isdir(path):
            return {"error": "Not a directory"}
        
        items = []
        for item in os.listdir(path):
            item_path = os.path.join(path, item)
            is_dir = os.path.isdir(item_path)
            items.append({
                "name": item,
                "path": item_path,
                "is_dir": is_dir
            })
        
        # Sort directories first, then files
        items.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))
        
        return {
            "current_path": path,
            "parent_path": os.path.dirname(path) if path != home_dir else None,
            "items": items
        }
    except Exception as e:
        return {"error": str(e)}

# Routes
@app.route('/')
def index():
    projects = load_projects()
    return render_template('index.html', home_dir=get_home_directory(), projects=projects)

@app.route('/browse', methods=['POST'])
def browse_directory():
    try:
        path = request.form.get('path', get_home_directory())
        result = list_directory(path)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/create_project', methods=['POST'])
def create_project():
    try:
        project_name = request.form.get('project_name', '').strip()
        project_dir = request.form.get('project_dir', '').strip()
        is_drf = 'is_drf' in request.form
        apps = [app.strip() for app in request.form.getlist('apps') if app.strip()]
        
        if not project_name:
            raise ValueError("Project name is required")
        if not project_dir:
            raise ValueError("Project directory is required")
        if not os.path.isdir(project_dir):
            raise ValueError("Project directory does not exist")
        
        project_path = create_django_project(project_name, project_dir, is_drf, apps)
        
        # Save project to database
        projects = load_projects()
        new_project = {
            'id': str(uuid.uuid4()),
            'name': project_name,
            'path': project_path,
            'is_drf': is_drf,
            'apps': apps,
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat()
        }
        projects.append(new_project)
        save_projects(projects)
        
        flash(f"Project '{project_name}' created successfully!", 'success')
        return redirect(url_for('manage_project', project_id=new_project['id']))
        
    except Exception as e:
        flash(f"Error: {str(e)}", 'danger')
        return redirect(url_for('index'))

@app.route('/projects')
def list_projects():
    projects = load_projects()
    return render_template('projects.html', projects=projects)

@app.route('/project/<project_id>')
def manage_project(project_id):
    try:
        project = get_project_by_id(project_id)
        if not project:
            flash("Project not found", "danger")
            return redirect(url_for('list_projects'))
        
        if not os.path.exists(project['path']):
            flash("Project directory does not exist", "danger")
            return redirect(url_for('list_projects'))
        
        apps = get_installed_apps(project['path'])
        
        return render_template('manage.html', 
                              project=project,
                              apps=apps)
    except Exception as e:
        flash(f"Error: {str(e)}", 'danger')
        return redirect(url_for('list_projects'))

@app.route('/project/<project_id>/add_app', methods=['POST'])
def add_app(project_id):
    try:
        project = get_project_by_id(project_id)
        if not project:
            raise ValueError("Project not found")
        
        app_name = request.form.get('app_name', '').strip()
        if not app_name:
            raise ValueError("App name is required")
        
        add_app_to_project(project['path'], app_name)
        
        # Update project data
        if app_name not in project['apps']:
            project['apps'].append(app_name)
            project['updated_at'] = datetime.now().isoformat()
            update_project(project_id, apps=project['apps'], updated_at=project['updated_at'])
        
        flash(f"App '{app_name}' added successfully!", 'success')
        
    except Exception as e:
        flash(f"Error: {str(e)}", 'danger')
    
    return redirect(url_for('manage_project', project_id=project_id))

@app.route('/project/<project_id>/remove_app', methods=['POST'])
def remove_app(project_id):
    try:
        project = get_project_by_id(project_id)
        if not project:
            raise ValueError("Project not found")
        
        app_name = request.form.get('app_name', '').strip()
        if not app_name:
            raise ValueError("App name is required")
        
        remove_app_from_project(project['path'], app_name)
        
        # Update project data
        if app_name in project['apps']:
            project['apps'].remove(app_name)
            project['updated_at'] = datetime.now().isoformat()
            update_project(project_id, apps=project['apps'], updated_at=project['updated_at'])
        
        flash(f"App '{app_name}' removed successfully!", 'success')
        
    except Exception as e:
        flash(f"Error: {str(e)}", 'danger')
    
    return redirect(url_for('manage_project', project_id=project_id))

@app.route('/project/<project_id>/update', methods=['POST'])
def update_project_details(project_id):
    try:
        project = get_project_by_id(project_id)
        if not project:
            raise ValueError("Project not found")
        
        project_name = request.form.get('project_name', '').strip()
        if not project_name:
            raise ValueError("Project name is required")
        
        # Rename project directory if name changed
        if project_name != project['name']:
            old_path = project['path']
            new_path = os.path.join(os.path.dirname(old_path), project_name)
            
            if os.path.exists(new_path):
                raise ValueError("A project with this name already exists in the directory")
            
            # Rename directory
            os.rename(old_path, new_path)
            
            # Update settings.py
            settings_path = os.path.join(new_path, project['name'], 'settings.py')
            if os.path.exists(settings_path):
                with open(settings_path, 'r') as f:
                    content = f.read()
                
                # Update ROOT_URLCONF
                content = content.replace(
                    f"ROOT_URLCONF = '{project['name']}.urls'",
                    f"ROOT_URLCONF = '{project_name}.urls'"
                )
                
                # Update WSGI_APPLICATION
                content = content.replace(
                    f"WSGI_APPLICATION = '{project['name']}.wsgi.application'",
                    f"WSGI_APPLICATION = '{project_name}.wsgi.application'"
                )
                
                with open(settings_path, 'w') as f:
                    f.write(content)
            
            # Rename project directory inside
            os.rename(
                os.path.join(new_path, project['name']),
                os.path.join(new_path, project_name)
            )
            
            # Update project data
            update_project(
                project_id, 
                name=project_name, 
                path=new_path,
                updated_at=datetime.now().isoformat()
            )
        else:
            update_project(project_id, updated_at=datetime.now().isoformat())
        
        flash("Project updated successfully!", 'success')
        
    except Exception as e:
        flash(f"Error: {str(e)}", 'danger')
    
    return redirect(url_for('manage_project', project_id=project_id))

@app.route('/project/<project_id>/delete', methods=['POST'])
def delete_project_route(project_id):
    try:
        if delete_project(project_id):
            flash("Project deleted successfully!", 'success')
        else:
            flash("Project not found", 'danger')
    except Exception as e:
        flash(f"Error: {str(e)}", 'danger')
    
    return redirect(url_for('list_projects'))

@app.route('/api/apps/<project_id>')
def api_apps(project_id):
    try:
        project = get_project_by_id(project_id)
        if not project:
            return jsonify({"error": "Project not found"}), 404
        
        apps = get_installed_apps(project['path'])
        return jsonify({"apps": apps})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Error handlers
@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Not found"}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({"error": "Internal server error"}), 500

if __name__ == '__main__':
    app.run(debug=True)