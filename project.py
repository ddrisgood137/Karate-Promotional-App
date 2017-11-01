from datetime import date
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter, A4
from PyPDF2 import PdfFileReader, PdfFileWriter
from flask import Flask, render_template, request, redirect, jsonify, url_for, flash
from sqlalchemy import create_engine, asc
from sqlalchemy.orm import sessionmaker
from database_setup import Base, Promotional, Application, Pairing
from flask import session as login_session
import random
import string
from oauth2client.client import flow_from_clientsecrets
from oauth2client.client import FlowExchangeError
import httplib2
import json
from flask import make_response
import requests
import StringIO

app = Flask(__name__)

CLIENT_ID = json.loads(
    open('client_secrets.json', 'r').read())['web']['client_id']
APPLICATION_NAME = "Karate Promotional Organizer"


# Connect to Database and create database session
engine = create_engine('sqlite:///promotional.db')
Base.metadata.bind = engine

DBSession = sessionmaker(bind=engine)
session = DBSession()

errors = {"1":"Error: Duplicate"}

@app.route('/welcome')
def welcome():
    return render_template('welcome.html')

@app.route('/home')
def home():
    promotionals = session.query(Promotional).order_by(asc(Promotional.date))
    return render_template('home.html', title="Shinkyu Shotokan Promotional Builder", promotionals=promotionals)

@app.route('/addPromotional', methods=['GET', 'POST'])
def addPromotional():
    if request.method == 'POST':
        newPromotional = Promotional(
            date=request.form['promotionalDate'], type=request.form['type'])
        session.add(newPromotional)
        # flash('New Promotional %s Successfully Created' % newPromotional.name)
        session.commit()
        return redirect(url_for('home'))

@app.route('/<int:promotional_id>', methods=['GET', 'POST'])
def showPromotional(promotional_id):
    promotional = session.query(Promotional).filter_by(id=promotional_id).one()
    applications = session.query(Application).filter_by(promotional_id=promotional_id).order_by(Application.lastName).all()
    title = promotional.date.strftime("%B %d, %Y") + " - " + promotional.type
    return render_template('promotional.html', title=title, promotional_id=promotional_id, applications=applications)

@app.route('/<int:promotional_id>/<string:color>', methods=['GET', 'POST'])
def showPromotionalColor(promotional_id, color):
    promotional = session.query(Promotional).filter_by(id=promotional_id).one()
    applications = session.query(Application).filter_by(promotional_id=promotional_id, color=color).order_by(Application.lastName).all()
    unmatchedApplications = session.query(Application).filter_by(promotional_id=promotional_id, color=color, pairingA=None, pairingB=None).order_by(Application.lastName).all()
    existingPairings = session.query(Pairing).filter_by(promotional_id=promotional_id, color=color).all()
    title = promotional.date.strftime("%B %d, %Y") + " - " + promotional.type + ": " + color

    error = None
    if request.args.get('error') != None:
    		error = errors[request.args.get('error')] 

    def makeSelect(selected, name):
        if selected != None:
            select = "<select name='%s'>" % name
            endSelect = "</select>"

            for application in applications:
                fullName = application.fullName
                value = application.id
                if application == selected:
                    option = "<option value='%s' selected>%s</option>" % (value, fullName)
                else:
                    option = "<option value='%s'>%s</option>" % (value, fullName)
                select = select + option

            select = select + endSelect
        else:
            select = None
        return select
    
    pairings = []
    for pairing in existingPairings:
        sideA = pairing.application_A
        sideB = pairing.application_B

        if sideB == None and len(unmatchedApplications) > 0:
            sideB = unmatchedApplications.pop(0)

        tup = {"sideA":makeSelect(sideA, str(existingPairings.index(pairing)) + "sideA"),"sideB":makeSelect(sideB, str(existingPairings.index(pairing)) + "sideB")}
        print tup
        pairings.append(tup)

    if len(unmatchedApplications) > 0:
        i = 0
        name = len(existingPairings)
        while i < len(unmatchedApplications):
            tup = {"sideA":makeSelect(unmatchedApplications[i], str(name) + "sideA"),"sideB":makeSelect(unmatchedApplications[i+1], str(name) + "sideB") if i+1 < len(unmatchedApplications) else None}
            i += 2
            name += 1
            pairings.append(tup)

    return render_template('promotional.html', title=title, promotional_id=promotional_id, applications=applications, color=color, pairings=pairings, error=error)



@app.route('/<int:promotional_id>/<string:color>/certificates', methods=['GET', 'POST'])
def generateCertificates(promotional_id, color):
    promotional = session.query(Promotional).filter_by(id=promotional_id).one()
    #yellow = session.query(Application).filter_by(promotional_id=promotional_id, color="yellow").order_by(Application.lastName).all()
    applications = session.query(Application).filter_by(promotional_id=promotional_id, color=color).order_by(Application.lastName).all()
    title = promotional.date.strftime("%B %d, %Y") + " - " + promotional.type + ": " + color

    output = PdfFileWriter()
    
    date = promotional.date.strftime("%B %d, %Y")

    for application in applications:
        name = application.firstName + " " + application.lastName
        certificate = PdfFileReader(open("promotionalCertificate.pdf", "rb"))
        certificatePage = certificate.getPage(0)
        
        infoBuffer = StringIO.StringIO()
        
        def hello(c):
            c.setFont('Helvetica', 24)
            c.drawCentredString(305,452, name)
            c.setFont('Helvetica', 36)
            c.drawCentredString(305,372, application.rank)
            c.setFont('Helvetica', 15)
            c.drawString(180,330, date)
            c.drawCentredString(200,285,"Sensei Sue, Sensei Nobu")

        c = canvas.Canvas(infoBuffer)

        hello(c)
        c.showPage()
        c.save()
        
        infoBuffer.seek(0)
        info = PdfFileReader(infoBuffer)
        certificatePage.mergePage(info.getPage(0))
        output.addPage(certificatePage)
        infoBuffer.close()

    outputStream = StringIO.StringIO()
    output.write(outputStream)

    pdfOut = outputStream.getvalue()
    outputStream.close()
    
    fileName = color + " certificates.pdf"
    
    response = make_response(pdfOut)
    response.headers['Content-Disposition'] = "attachment; filename=" + fileName
    response.mimetype = 'application/pdf'
    return response

    #return render_template('promotional.html', title=title, promotional_id=promotional_id, applications=applications, color=color)

@app.route('/<int:promotional_id>/<string:color>/judgesPackets', methods=['GET', 'POST'])
def generateJudgesPackets(promotional_id, color):
    promotional = session.query(Promotional).filter_by(id=promotional_id).one()
    #yellow = session.query(Application).filter_by(promotional_id=promotional_id, color="yellow").order_by(Application.lastName).all()
    applications = session.query(Application).filter_by(promotional_id=promotional_id, color=color).order_by(Application.lastName).order_by(Application.rank).all()
    title = promotional.date.strftime("%B %d, %Y") + " - " + promotional.type + ": " + color

    output = PdfFileWriter()
    infoBuffer = StringIO.StringIO()
    c = canvas.Canvas(infoBuffer)
    date = promotional.date.strftime("%B %d, %Y")
    judgesPacket = PdfFileReader(open("RankingSheet.pdf", "rb"))
    judgesPacketPage = judgesPacket.getPage(0)
    counter = 0
    previousRank = applications[0].rank

    for application in applications:
        name = application.firstName + " " + application.lastName

        if counter == 4 or previousRank != application.rank:
            counter = 0
            c.showPage()
            c.save()

            infoBuffer.seek(0)
            info = PdfFileReader(infoBuffer)
            judgesPacketPage.mergePage(info.getPage(0))
            output.addPage(judgesPacketPage)
            infoBuffer.close()

            infoBuffer = StringIO.StringIO()
            c = canvas.Canvas(infoBuffer)
            judgesPacket = PdfFileReader(open("RankingSheet.pdf", "rb"))
            judgesPacketPage = judgesPacket.getPage(0)

        if counter == 0:
            c.setFont('Helvetica', 24)
            c.drawCentredString(300, 700, application.rank + " " + color.title() + " Belt")
            c.setFont('Helvetica', 12)
            c.drawCentredString(450, 566, name)
            counter += 1
        elif counter == 1:
            c.setFont('Helvetica', 12)
            c.drawCentredString(450, 417, name)
            counter += 1
        elif counter == 2:
            c.setFont('Helvetica', 12)
            c.drawCentredString(450, 270, name)
            counter += 1
        elif counter == 3:
            c.setFont('Helvetica', 12)
            c.drawCentredString(450, 115, name)
            counter += 1

        if applications.index(application) == len(applications)-1:
            counter = 0
            c.showPage()
            c.save()

            info = PdfFileReader(infoBuffer)
            judgesPacketPage.mergePage(info.getPage(0))
            output.addPage(judgesPacketPage)

            infoBuffer = StringIO.StringIO()

        previousRank = application.rank
        # infoBuffer.seek(0)
        # info = PdfFileReader("output.pdf")
        # judgesPacketPage.mergePage(info.getPage(0))
        # output.addPage(judgesPacketPage)
        #infoBuffer.close()

    outputStream = StringIO.StringIO()
    output.write(outputStream)

    pdfOut = outputStream.getvalue()
    outputStream.close()

    fileName = color + " judgesPacket.pdf"

    response = make_response(pdfOut)
    response.headers['Content-Disposition'] = "attachment; filename=" + fileName
    response.mimetype = 'application/pdf'
    return response
    #return render_template('promotional.html', title=title, promotional_id=promotional_id, applications=applications, color=color)

@app.route('/<int:promotional_id>/<string:color>/pairings', methods=['GET', 'POST'])
def updatePairings(promotional_id, color):
    if request.method == 'POST':
        print request.form
        session.query(Pairing).delete()

        existingApplications = []
        error = "1"
        i = 0
        while i <= len(request.form)/2:
            sideA_id=request.form[str(i)+"sideA"]

            if sideA_id in existingApplications:
            	return redirect(url_for('showPromotionalColor', promotional_id=promotional_id, color=color, error=error))

            existingApplications.append(sideA_id)

            if (str(i)+"sideB") in request.form:
                sideB_id=request.form[str(i)+"sideB"] 
                if sideB_id in existingApplications:
            		return redirect(url_for('showPromotionalColor', promotional_id=promotional_id, color=color, error=error))
            	existingApplications.append(sideB_id)
            else:
                sideB_id = None
            newPairing = Pairing(promotional_id=promotional_id, sideA_id=sideA_id, sideB_id=sideB_id, color=color)
            session.add(newPairing)
            i += 1

        session.commit()
        return redirect(url_for('showPromotionalColor', promotional_id=promotional_id, color=color, error=None))


@app.route('/<int:promotional_id>/addApplication', methods=['GET', 'POST'])
def addApplication(promotional_id):
    if request.method == 'POST':
        color = rank_to_belt(request.form['rank'])
        newApplication = Application(
            firstName=request.form['firstName'], lastName=request.form['lastName'], birthDate=request.form['birthDate'], rank=request.form['rank'],
                 color=color, promotional_id=promotional_id)
        session.add(newApplication)
        # flash('New Promotional %s Successfully Created' % newPromotional.name)
        session.commit()
        return redirect(url_for('showPromotional', promotional_id=promotional_id))

@app.route('/<int:promotional_id>/<int:application_id>/edit', methods=['GET', 'POST'])
def editApplication(promotional_id, application_id):
    editedApplication = session.query(Application).filter_by(id=application_id).one()
    promotional = session.query(Promotional).filter_by(id=promotional_id).one()
    
    if request.method == 'POST':
        if request.form['firstName']:
            editedApplication.name = request.form['lastName']
        if request.form['lastName']:
            editedApplication.description = request.form['lastName']
        if request.form['birthDate']:
            editedApplication.price = request.form['birthDate']
        if request.form['rank']:
        	editedApplication.rank = request.form['rank']
       
        session.add(editedApplication)
        session.commit()
        flash('Application Successfully Edited')
        return redirect(url_for('showPromotional', promotional_id=promotional_id))
    else:
        return render_template('editapplication.html', promotional_id=promotional_id, application_id=application_id, application=editedApplication)


def rank_to_belt(argument):
    switcher = {
        "10thkyu": "yellow",
        "9thkyu": "blue",
        "8thkyu": "blue",
        "7thkyu": "green",
        "6thkyu": "green",
        "5thkyu": "purple",
        "4thkyu": "purple",
        "3rdkyu": "brown",
        "2ndkyu": "brown",
        "1stkyu": "brown",
        "1stdan": "black",
        "2nddan": "black",
        "3rddan": "black",
        "4thdan": "black",
        "5thdan": "black",
        "6thdan": "black",
        "7thdan": "black",
        "8thdan": "black",
        "9thdan": "black",
        "10thdan": "black"
    }
    return switcher.get(argument, "nothing")

if __name__ == '__main__':
    app.secret_key = 'super_secret_key'
    app.debug = True
    app.run(host='0.0.0.0', port=5000)
