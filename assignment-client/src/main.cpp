//  Tivoli Cloud VR
//  Copyright (C) 2020, Tivoli Cloud VR, Inc
//  
//  This program is free software: you can redistribute it and/or modify
//  it under the terms of the GNU Affero General Public License as published by
//  the Free Software Foundation, either version 3 of the License, or
//  (at your option) any later version.
//  
//  This program is distributed in the hope that it will be useful,
//  but WITHOUT ANY WARRANTY; without even the implied warranty of
//  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
//  GNU Affero General Public License for more details.
//  
//  You should have received a copy of the GNU Affero General Public License
//  along with this program.  If not, see <http://www.gnu.org/licenses/>.
//  


#include <BuildInfo.h>
#include <SharedUtil.h>

#include "AssignmentClientApp.h"

int main(int argc, char* argv[]) {
    setupHifiApplication(BuildInfo::ASSIGNMENT_CLIENT_NAME);

    AssignmentClientApp app(argc, argv);
    
    int acReturn = app.exec();
    qDebug() << "assignment-client process" <<  app.applicationPid() << "exiting with status code" << acReturn;

    qInfo() << "Quitting.";
    return acReturn;
}
