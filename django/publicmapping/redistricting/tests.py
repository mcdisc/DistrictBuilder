"""
Define a set of tests for the redistricting app.

Test coverage is provided for the complex geographice queries and routines
in the redistricting app.

This file is part of The Public Mapping Project
http://sourceforge.net/projects/publicmapping/

License:
    Copyright 2010 Micah Altman, Michael McDonald

    Licensed under the Apache License, Version 2.0 (the "License");
    you may not use this file except in compliance with the License.
    You may obtain a copy of the License at

        http://www.apache.org/licenses/LICENSE-2.0

    Unless required by applicable law or agreed to in writing, software
    distributed under the License is distributed on an "AS IS" BASIS,
    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
    See the License for the specific language governing permissions and
    limitations under the License.

Author: 
    Andrew Jennings, David Zwarg, Kenny Shepard
"""

import os
from django.test import TestCase
import zipfile
from django.db.models import Sum as SumAgg, Min, Max
from django.test.client import Client
from django.contrib.gis.geos import *
from django.contrib.auth.models import User
from publicmapping.redistricting.models import *
from publicmapping.redistricting.utils import *
from publicmapping.redistricting.calculators import *
from django.conf import settings
from datetime import datetime

class BaseTestCase(TestCase):
    """
    Only contains setUp and tearDown, which are shared among all other TestCases
    """
    fixtures = ['redistricting_testdata.json']

    def setUp(self):
        """
        Setup the general tests. This fabricates a set of data in the 
        test database for use later.
        """
        # need geounits for ids & geometries
        self.geolevels = Geolevel.objects.filter( 
            Q(name='first level') |
            Q(name='second level') |
            Q(name='third level')
        ).order_by('id')
        self.geolevels = list(self.geolevels)

        # create a Subject
        self.subject1 = Subject.objects.get(name='TestSubject')
        self.subject2 = Subject.objects.get(name='TestSubject2')
        
        self.geounits = {}

        # create a three-tiered 27x27 square grid of geounits with coords from (0,0) to (1,1)
        for gl in self.geolevels:
            self.geounits[gl.id] = list(Geounit.objects.filter(geolevel=gl).order_by('id'))

        # create a User
        self.username = 'test_user'
        self.password = 'secret'
        self.user = User.objects.get(username=self.username)

        # create a LegislativeBody
        self.legbod = LegislativeBody.objects.get(name='TestLegislativeBody')

        # create a Target
        self.target = Target.objects.get(subject=self.subject1)

        # create a LegislativeDefault
        self.legdef = LegislativeDefault.objects.get(legislative_body=self.legbod, target=self.target)

        # create LegislativeLevel hierarchy
        self.leglev3 = LegislativeLevel.objects.get(geolevel=self.geolevels[2])
        self.leglev2 = LegislativeLevel.objects.get(geolevel=self.geolevels[1])
        self.leglev1 = LegislativeLevel.objects.get(geolevel=self.geolevels[0])
        
        # create a Plan
        self.plan = Plan.objects.get(name='testPlan')

        # create Districts
        self.district1 = District.objects.get(name='District 1')
        self.district2 = District.objects.get(name='District 2')



class ScoringTestCase(BaseTestCase):
    """
    Unit tests to test the logic of the scoring functionality
    """
    def setUp(self):
        BaseTestCase.setUp(self)

        # create a couple districts and populate with geounits
        geounits = self.geounits[self.geolevels[1].id]

        self.dist1units = geounits[0:3] + geounits[9:12]
        self.dist2units = geounits[18:21] + geounits[27:30] + geounits[36:39]

        dist1ids = map(lambda x: str(x.id), self.dist1units)
        dist2ids = map(lambda x: str(x.id), self.dist2units)

        self.plan.add_geounits(self.district1.district_id, dist1ids, self.geolevels[1].id, self.plan.version)
        self.plan.add_geounits(self.district2.district_id, dist2ids, self.geolevels[1].id, self.plan.version)

        self.district1 = max(District.objects.filter(plan=self.plan,district_id=self.district1.district_id),key=lambda d: d.version)
        self.district2 = max(District.objects.filter(plan=self.plan,district_id=self.district2.district_id),key=lambda d: d.version)
        
        # create objects used for scoring
        self.scoreDisplay1 = ScoreDisplay(title='SD1', legislative_body=self.legbod, is_page=False)
        self.scoreDisplay1.save()

        self.scorePanel1 = ScorePanel(type='district', display=self.scoreDisplay1, position=0, title='SP1')
        self.scorePanel1.save()

    def tearDown(self):
        """
        Clean up after testing.
        """
        BaseTestCase.tearDown(self)
        self.scorePanel1.delete()
        self.scoreDisplay1.delete()

    def testSetup(self):
        """
        Make sure we have the districts created during setUp
        """
        district1units = self.district1.get_base_geounits()
        self.assertEqual(54, len(district1units), 'Incorrect number of geounits returned in dist1: %d' % len(district1units))

        district2units = self.district2.get_base_geounits()
        self.assertEqual(81, len(district2units), 'Incorrect number of geounits returned in dist1: %d' % len(district2units))

    def testInvalidScenarios(self):
        """
        Test what happens when a calculator module doesn't exist,
        or bad parameters are passed in
        """
        badFunction = ScoreFunction(calculator='does.not.Exist', name='bad')
        self.assertRaises(ImportError, badFunction.score, [self.district1])

    def testSchwarzbergScoringFunction(self):
        """
        Test the schwarzberg scoring function
        """
        # create the ScoreFunction
        schwartzFunction = ScoreFunction(calculator='redistricting.calculators.Schwartzberg', name='SchwartzbergFn')

        # multiple districts
        scores = schwartzFunction.score([self.district1, self.district2])
        self.assertAlmostEquals(0.86832150547, scores[0], 9, 'Schwartzberg for first district was incorrect: %f' % scores[0])
        self.assertAlmostEquals(0.88622692545, scores[1], 9, 'Schwartzberg for second district was incorrect: %f' % scores[1])

        # single district as list
        scores = schwartzFunction.score([self.district1])
        self.assertAlmostEquals(0.86832150547, scores[0], 9, 'Schwartzberg for District 1 was incorrect: %f' % scores[0])

        # single district as object
        score = schwartzFunction.score(self.district1)
        self.assertAlmostEquals(0.86832150547, score, 9, 'Schwartzberg for District 1 was incorrect: %f' % score)

        # HTML
        score = schwartzFunction.score(self.district1, 'html')
        self.assertEquals("86.83%", score, 'Schwartzberg HTML for District 1 was incorrect: ' + score)

        # JSON
        score = schwartzFunction.score(self.district1, 'json')
        self.assertEquals('{"result": 0.86832150546992093}', score, 'Schwartzberg JSON for District 1 was incorrect: ' + score)

    def testSumFunction(self):
        """
        Test the sum scoring function
        """
        # create the scoring function for summing three parameters
        sumThreeFunction = ScoreFunction(calculator='redistricting.calculators.Sum', name='SumThreeFn')
        sumThreeFunction.save()

        # create the arguments
        ScoreArgument(function=sumThreeFunction, argument='value1', value='0', type='literal').save()
        ScoreArgument(function=sumThreeFunction, argument='value2', value='1', type='literal').save()
        ScoreArgument(function=sumThreeFunction, argument='value3', value='2', type='literal').save()

        # test raw value
        score = sumThreeFunction.score(self.district1)
        self.assertEquals(3, score, 'sumThree was incorrect: %d' % score)

        # HTML -- also make sure mixed case format works
        score = sumThreeFunction.score(self.district1, 'HtmL')
        self.assertEquals('<span>3.0</span>', score, 'sumThree was incorrect: %s' % score)

        # JSON -- also make sure uppercase format works
        score = sumThreeFunction.score(self.district1, 'JSON')
        self.assertEquals('{"result": 3.0}', score, 'sumThree was incorrect: %s' % score)

        # create the scoring function for summing a literal and a subject
        sumMixedFunction = ScoreFunction(calculator='redistricting.calculators.Sum', name='SumMixedFn')
        sumMixedFunction.save()

        # create the arguments
        ScoreArgument(function=sumMixedFunction, argument='value1', value=self.subject1.name, type='subject').save()
        ScoreArgument(function=sumMixedFunction, argument='value2', value='5.0', type='literal').save()

        # test raw value
        score = sumMixedFunction.score(self.district1)
        self.assertEquals(11, score, 'sumMixed was incorrect: %d' % score)

    def testSumPlanFunction(self):
        """
        Test the sum scoring function on a plan level
        """
        # create the scoring function for summing the districts in a plan
        sumPlanFunction = ScoreFunction(calculator='redistricting.calculators.Sum', name='SumPlanFn', is_planscore=True)
        sumPlanFunction.save()

        # create the arguments
        ScoreArgument(function=sumPlanFunction, argument='value1', value='1', type='literal').save()

        # test raw value
        num_districts = len(self.plan.get_districts_at_version(self.plan.version, include_geom=False))
        score = sumPlanFunction.score(self.plan)
        self.assertEquals(num_districts, score, 'sumPlanFunction was incorrect: %d' % score)

        # test a list of plans
        score = sumPlanFunction.score([self.plan, self.plan])
        self.assertEquals(num_districts, score[0], 'sumPlanFunction was incorrect for first plan: %d' % score[0])
        self.assertEquals(num_districts, score[1], 'sumPlanFunction was incorrect for second plan: %d' % score[1])

    def testThresholdFunction(self):
        # create the scoring function for checking if a value passes a threshold
        thresholdFunction1 = ScoreFunction(calculator='redistricting.calculators.Threshold', name='ThresholdFn')
        thresholdFunction1.save()

        # create the arguments
        ScoreArgument(function=thresholdFunction1, argument='value', value='1', type='literal').save()
        ScoreArgument(function=thresholdFunction1, argument='threshold', value='2', type='literal').save()

        # test raw value
        score = thresholdFunction1.score(self.district1)
        self.assertEquals(False, score, '1 is not greater than 2')

        # create a new scoring function to test the inverse
        thresholdFunction2 = ScoreFunction(calculator='redistricting.calculators.Threshold', name='ThresholdFn')
        thresholdFunction2.save()

        # create the arguments
        ScoreArgument(function=thresholdFunction2, argument='value', value='2', type='literal').save()
        ScoreArgument(function=thresholdFunction2, argument='threshold', value='1', type='literal').save()

        # test raw value
        score = thresholdFunction2.score(self.district1)
        self.assertEquals(True, score, '2 is greater than 1')

        # HTML
        score = thresholdFunction2.score(self.district1, 'html')
        self.assertEquals("<span>True</span>", score, 'Threshold HTML was incorrect: ' + score)

        # JSON
        score = thresholdFunction2.score(self.district1, 'json')
        self.assertEquals('{"result": true}', score, 'Threshold JSON was incorrect: ' + score)

    def testRangeFunction(self):
        # create the scoring function for checking if a value passes a range
        rangeFunction1 = ScoreFunction(calculator='redistricting.calculators.Range', name='RangeFn')
        rangeFunction1.save()

        # create the arguments
        ScoreArgument(function=rangeFunction1, argument='value', value='2', type='literal').save()
        ScoreArgument(function=rangeFunction1, argument='min', value='1', type='literal').save()
        ScoreArgument(function=rangeFunction1, argument='max', value='3', type='literal').save()

        # test raw value
        score = rangeFunction1.score(self.district1)
        self.assertEquals(True, score, '2 is between 1 and 3')

        # HTML
        score = rangeFunction1.score(self.district1, 'html')
        self.assertEquals("<span>True</span>", score, 'Range HTML was incorrect: ' + score)

        # JSON
        score = rangeFunction1.score(self.district1, 'json')
        self.assertEquals('{"result": true}', score, 'Range JSON was incorrect: ' + score)


class PlanTestCase(BaseTestCase):
    """
    Unit tests to test Plan operations
    """
    def test_district_id_increment(self):
        """
        Test the logic for the automatically generated district_id
        """
        # Note: district_id is set to 0 here, because otherwise, the auto-increment code does not get called.
        # It may be best to revisit how district_id is used throughout the app, and to not allow for it to be set,
        # since it should be auto-generated.
        d3 = District(name='District 3',district_id=0)
        d3.plan = self.plan
        d3.save()
        latest = d3.district_id
        d4 = District(name = 'District 4',district_id=0)
        d4.plan = self.plan
        d4.save()
        incremented = d4.district_id
        self.assertTrue(latest + 1 == incremented, 'New district did not have an id greater than the previous district')
        
    def test_add_to_plan(self):
        """
        Test the logic for adding geounits to a district.
        """
        district = self.district1
        districtid = district.district_id

        level = self.geolevels[0]
        levelid = level.id
        
        geounits = self.geounits[level.id]
        geounitids = [str(geounits[0].id)]

        self.plan.add_geounits(districtid, geounitids, levelid, self.plan.version)

        # Check for new geounits
        numunits = len(Plan.objects.get(pk=self.plan.id).get_base_geounits(0.1))
        self.assertEqual(81, numunits, 'Geounits not added to plan correctly')

    def test_unassigned(self):
        """
        Test the logic for an unassigned district.
        """
        unassigned = District.objects.filter(name='Unassigned', plan = self.plan)
        self.assertEqual(1, unassigned.count(), 'No Unassigned district on plan. (e:1, a:%d)' % unassigned.count())

    def test_copyplan(self):
        """
        Test the logic for copying plans.
        """
        district = self.district1
        districtid = district.district_id

        level = self.geolevels[0]
        levelid = level.id
        
        geounits = self.geounits[level.id]
        geounitids = [str(geounits[0].id)]

        # Add geounits to plan
        self.plan.add_geounits(districtid, geounitids, levelid, self.plan.version)
        
        # Login
        client = Client()
        client.login(username=self.username, password=self.password)

        # Issue copy command
        copyname = 'MyTestCopy'
        response = client.post('/districtmapping/plan/%d/copy/' % self.plan.id, { 'name':copyname })
        self.assertEqual(200, response.status_code, 'Copy handler didn\'t return 200:' + str(response))

        # Ensure copy exists
        copy = Plan.objects.get(name=copyname)
        self.assertNotEqual(copy, None, 'Copied plan doesn\'t exist')

        # Ensure districts are the same between plans
        numdistricts = len(self.plan.get_districts_at_version(self.plan.version))
        numdistrictscopy = len(copy.get_districts_at_version(copy.version))
        self.assertEqual(numdistricts, numdistrictscopy, 'Districts between original and copy are different. (e:%d, a:%d)' % (numdistricts, numdistrictscopy))

        # Ensure geounits are the same between plans
        numunits = len(Plan.objects.get(pk=self.plan.id).get_base_geounits(0.1))
        numunitscopy = len(Plan.objects.get(pk=copy.id).get_base_geounits(0.1))
        self.assertEqual(numunits, numunitscopy, 'Geounits between original and copy are different')

    def test_district_locking(self):
        """
        Test the logic for locking/unlocking a district.
        """
        district = self.district1
        districtid = district.id
        district_id = district.district_id
        
        level = self.geolevels[0]
        levelid = level.id
        
        geounits = self.geounits[level.id]
        geounitids = [str(geounits[0].id)]

        client = Client()

        # Create a second user, and try to lock a district not belonging to that user
        username2 = 'test_user2'
        user2 = User(username=username2)
        user2.set_password(self.password)
        user2.save()
        client.login(username=username2, password=self.password)

        # Issue lock command when not logged in
        response = client.post('/districtmapping/plan/%d/district/%d/lock/' % (self.plan.id, district_id), { 'lock':True, 'version':self.plan.version })
        self.assertEqual(403, response.status_code, 'Non-owner was able to lock district.' + str(response))
        
        # Login
        client.login(username=self.username, password=self.password)
        
        # Issue lock command
        response = client.post('/districtmapping/plan/%d/district/%d/lock/' % (self.plan.id, district_id), { 'lock':True, 'version':self.plan.version })
        self.assertEqual(200, response.status_code, 'Lock handler didn\'t return 200:' + str(response))

        # Ensure lock exists
        district = District.objects.get(pk=districtid)
        self.assertTrue(district.is_locked, 'District wasn\'t locked.' + str(response))

        # Try adding geounits to the locked district (not allowed)
        self.plan.add_geounits(district_id, geounitids, levelid, self.plan.version)
        numunits = len(Plan.objects.get(pk=self.plan.id).get_base_geounits(0.1))
        self.assertEqual(0, numunits, 'Geounits were added to a locked district. Num geounits: %d' % numunits)
        
        # Issue unlock command
        response = client.post('/districtmapping/plan/%d/district/%d/lock/' % (self.plan.id, district_id), { 'lock':False, 'version':self.plan.version })
        self.assertEqual(200, response.status_code, 'Lock handler didn\'t return 200:' + str(response))

        # Ensure lock has been removed
        district = District.objects.get(pk=districtid)
        self.assertFalse(district.is_locked, 'District wasn\'t unlocked.' + str(response))

        # Add geounits to the plan
        self.plan.add_geounits(district_id, geounitids, levelid, self.plan.version)
        numunits = len(Plan.objects.get(pk=self.plan.id).get_base_geounits(0.1))
        self.assertEqual(81, numunits, 'Geounits could not be added to an unlocked district. Num geounits: %d' % numunits)

    def test_district_locking2(self):
        """
        Test the case where adding a partially selected geometry (due to
        locking) may add the entire geometry's aggregate value.
        """
        geounits = self.geounits[self.geolevels[1].id]

        dist1ids = geounits[0:3] + geounits[9:12]
        dist2ids = geounits[18:21] + geounits[27:30] + geounits[36:39]

        dist1ids = map(lambda x: str(x.id), dist1ids)
        dist2ids = map(lambda x: str(x.id), dist2ids)

        self.plan.add_geounits(self.district1.district_id, dist1ids, self.geolevels[1].id, self.plan.version)
        self.plan.add_geounits(self.district2.district_id, dist2ids, self.geolevels[1].id, self.plan.version)

        district1 = max(District.objects.filter(plan=self.plan,district_id=self.district1.district_id),key=lambda d: d.version)
        district1units = district1.get_base_geounits(0.1)

        self.assertEqual(54, len(district1units), 'Incorrect number of geounits returned in dist1: %d' % len(district1units))

        district2 = max(District.objects.filter(plan=self.plan,district_id=self.district2.district_id),key=lambda d: d.version)
        district2units = district2.get_base_geounits(0.1)

        self.assertEqual(81, len(district2units), 'Incorrect number of geounits returned in dist2: %d' % len(district2units))

        geounits = self.geounits[self.geolevels[0].id] 
        dist3ids = geounits[1:3] + geounits[4:6] + geounits[7:9]

        dist3ids = map(lambda x: str(x.id), dist3ids)

        self.plan.add_geounits(self.district2.district_id + 1, dist3ids, self.geolevels[0].id, self.plan.version)

        district3 = max(District.objects.filter(plan=self.plan,district_id=self.district2.district_id+1),key=lambda d: d.version)
        district3units = district3.get_base_geounits(0.1)

        self.assertEqual(486, len(district3units), 'Incorrect number of geounits returned in dist3: %d' % len(district3units))

        # Plan looks like this now:
        #
        #  *-----------*-----------*-----------*
        #  |           |                       |
        #  |           |                       |
        #  |           |                       |
        #  |           |                       | 
        #  |           |                       |
        #  *           *           *           *
        #  |           |                       |
        #  |           |                       |
        #  +-----------+      District 3       |
        #  |           |                       |
        #  | District 2|                       |
        #  *           *           *           *
        #  |           |                       |
        #  +-----------+                       |
        #  |           |                       |
        #  | District 1|                       |
        #  |           |                       |
        #  *-----------*-----------*-----------*

        # Try locking District 2, selecting the large block that totally
        # contains District 1, and add it to District 3
        district2.is_locked = True
        district2.save()

        districtpre_computed = ComputedCharacteristic.objects.filter(district__in=[district1,district2,district3],subject=self.subject1).order_by('district').values_list('number',flat=True)
        presum = 0;
        for pre in districtpre_computed:
            presum += pre

        self.plan.add_geounits(district3.district_id, [str(geounits[0].id)], self.geolevels[0].id, self.plan.version)


        district1 = max(District.objects.filter(plan=self.plan,district_id=self.district1.district_id),key=lambda d: d.version)
        district2 = max(District.objects.filter(plan=self.plan,district_id=self.district2.district_id),key=lambda d: d.version)
        district3 = max(District.objects.filter(plan=self.plan,district_id=district3.district_id),key=lambda d: d.version)

        districtpost_computed = ComputedCharacteristic.objects.filter(district__in=[district1,district2,district3],subject=self.subject1).order_by('district').values_list('number',flat=True)
        postsum = 0;
        for post in districtpost_computed:
            postsum += post

        self.assertEqual(presum, postsum, 'The computed districts of the new plan do not match the computed districts of the old plan, when only reassigning geography. (e:%0.2f,a:%0.2f)' % (presum, postsum))

    def test_get_base_geounits(self):
        """
        Test getting base geounits
        """
        geounits = self.geounits[self.geolevels[0].id]

        dist1ids = [str(geounits[0].id)]
        dist2ids = [str(geounits[1].id)]

        self.plan.add_geounits(self.district1.district_id, dist1ids, self.geolevels[0].id, self.plan.version)
        self.plan.add_geounits(self.district2.district_id, dist2ids, self.geolevels[0].id, self.plan.version)

        # Test getting the base geounits for a district
        district1 = max(District.objects.filter(plan=self.plan,district_id=self.district1.district_id),key=lambda d: d.version)
        district1units = district1.get_base_geounits(0.1)
        self.assertEqual(81, len(district1units), 'Incorrect number of geounits returned in dist1: %d' % len(district1units))

        district2 = max(District.objects.filter(plan=self.plan,district_id=self.district2.district_id),key=lambda d: d.version)
        district2units = district2.get_base_geounits(0.1)
        self.assertEqual(81, len(district2units), 'Incorrect number of geounits returned in dist2: %d' % len(district2units))

        # Test getting the base geounits for a plan
        plan = Plan.objects.get(pk=self.plan.id)
        planunits = plan.get_base_geounits(0.1)
        self.assertEqual(162, len(planunits), 'Incorrect number of geounits returned in plan: %d' % len(planunits))

        # Test sorting the units by geounit id
        planunits.sort(key=lambda unit: unit[0])
        lastid = 0
        for unit in planunits:
            self.assertTrue(unit[0] >= lastid, 'Not in order: %d < %d' % (unit[0], lastid))
            lastid = unit[0]

        # Test getting assigned geounits
        assigned = plan.get_assigned_geounits(0.1)
        self.assertEqual(162, len(assigned), 'Incorrect number of assigned geounits returned: %d' % len(assigned))

        # Test getting unassigned geounits
        unassigned = plan.get_unassigned_geounits(0.1)
        self.assertEqual(729 - 162, len(unassigned), 'Incorrect number of unassigned geounits returned: %d' % len(unassigned))

    def test_plan2index(self):
        """
        Test exporting a plan
        """
        geounits = self.geounits[self.geolevels[0].id]
        dist1ids = [str(geounits[0].id)]
        self.plan.add_geounits(self.district1.district_id, dist1ids, self.geolevels[0].id, self.plan.version)

        plan = Plan.objects.get(pk=self.plan.id)
        archive = DistrictIndexFile.plan2index(plan)
        zin = zipfile.ZipFile(archive.name, "r")
        strz = zin.read(plan.name + ".csv")
        zin.close()
        os.remove(archive.name)
        self.assertEqual(891, len(strz), 'Index file was the wrong length: %d' % len(strz))

    def test_sorted_district_list(self):
        """
        Test the sorted district list for reporting
        """
        geounits = self.geounits[self.geolevels[0].id]
        dist1ids = [str(geounits[0].id)]
        self.plan.add_geounits(self.district1.district_id, dist1ids, self.geolevels[0].id, self.plan.version)
        plan = Plan.objects.get(pk=self.plan.id)

        mapping = plan.get_base_geounits()
        mapping.sort(key=lambda unit: unit[0])

        geolevel = plan.legislative_body.get_base_geolevel()
        geounits = Geounit.objects.filter(geolevel=geolevel)
        max_and_min = geounits.aggregate(Min('id'), Max('id'))
        min_id = int(max_and_min['id__min'])
        max_id = int(max_and_min['id__max'])

        sorted_district_list = list()
        row = None
        if len(mapping) > 0:
             row = mapping.pop(0)
        for i in range(min_id, max_id + 1):
            if row and row[0] == i:
                district_id = row[2]
                row = None
                if len(mapping) > 0:
                    row = mapping.pop(0)
            else:
                district_id = 'NA'
            sorted_district_list.append(district_id)

        self.assertEqual(729, len(sorted_district_list), 'Sorted district list was the wrong length: %d' % len(sorted_district_list))

    def test_schwartzberg(self):
        """
        Test the Schwartzberg measure of compactness.
        """
        geounits = self.geounits[self.geolevels[1].id]

        dist1ids = geounits[0:3] + geounits[9:12]
        dist2ids = geounits[18:21] + geounits[27:30] + geounits[36:39]

        dist1ids = map(lambda x: str(x.id), dist1ids)
        dist2ids = map(lambda x: str(x.id), dist2ids)

        self.plan.add_geounits(self.district1.district_id, dist1ids, self.geolevels[1].id, self.plan.version)
        self.plan.add_geounits(self.district2.district_id, dist2ids, self.geolevels[1].id, self.plan.version)

        district1 = max(District.objects.filter(plan=self.plan,district_id=self.district1.district_id),key=lambda d: d.version)
        district2 = max(District.objects.filter(plan=self.plan,district_id=self.district2.district_id),key=lambda d: d.version)

        calc = Schwartzberg()

        calc.compute(district=district1)
        self.assertAlmostEquals(0.86832150547, calc.result, 9, 'Schwartzberg for District 1 was incorrect: %d' % calc.result)

        calc.compute(district=district2)
        self.assertAlmostEquals(0.88622692545, calc.result, 9, 'Schwartzberg for District 2 was incorrect: %d' % calc.result)

    def test_schwartzberg1(self):
        """
        Test the Schwartzberg measure of compactness.
        """
        geounits = self.geounits[self.geolevels[1].id]

        dist1ids = geounits[0:3] + geounits[9:12]
        dist2ids = geounits[18:21] + geounits[27:30] + geounits[36:39]

        dist1ids = map(lambda x: str(x.id), dist1ids)
        dist2ids = map(lambda x: str(x.id), dist2ids)

        self.plan.add_geounits(self.district1.district_id, dist1ids, self.geolevels[1].id, self.plan.version)
        self.plan.add_geounits(self.district2.district_id, dist2ids, self.geolevels[1].id, self.plan.version)

        district1 = max(District.objects.filter(plan=self.plan,district_id=self.district1.district_id),key=lambda d: d.version)
        district2 = max(District.objects.filter(plan=self.plan,district_id=self.district2.district_id),key=lambda d: d.version)

        calc = Schwartzberg()

        calc.compute(plan=self.plan)
        self.assertAlmostEquals(0.87727421546, calc.result, 9, 'Schwartzberg for District 1 was incorrect: %f' % calc.result)


class GeounitMixTestCase(BaseTestCase):
    """
    Unit tests to test the mixed geounit spatial queries.
    """
    
    def test_numgeolevels(self):
        """
        Test the number of geolevels created.
        """
        self.assertEquals(3, len(self.geolevels), 'Number of geolevels for mixed geounits is incorrect.')

    def test_numgeounits1(self):
        """
        Test the number of geounits in the first tier of geounits.
        """
        self.assertEquals(9, len(self.geounits[self.geolevels[0].id]), 'Number of geounits at geolevel "%s" is incorrect.' % self.geolevels[0].name)

    def test_numgeounits2(self):
        """
        Test the number of geounits in the second tier of geounits.
        """
        self.assertEquals(81, len(self.geounits[self.geolevels[1].id]), 'Number of geounits at geolevel "%s" is incorrect.' % self.geolevels[1].name)

    def test_numgeounits3(self):
        """
        Test the number of geounits in the third tier of geounits.
        """
        self.assertEquals(729, len(self.geounits[self.geolevels[2].id]), 'Number of geounits at geolevel "%s" is incorrect.' % self.geolevels[2].name)

    def test_allunitscount(self):
        """
        Test that known geounits are spatially contained within other geounits.
        """
        unit1 = self.geounits[self.geolevels[0].id][0]

        unit2 = self.geounits[self.geolevels[1].id][0]

        self.assertTrue(unit1.geom.contains(unit2.geom), 'First unit does not contain secont unit.')

        unit3 = self.geounits[self.geolevels[2].id][0]

        self.assertTrue(unit1.geom.contains(unit3.geom), 'First unit does not contain second unit.')
        self.assertTrue(unit2.geom.contains(unit3.geom), 'Second unit does not contain third unit.')

    def test_get_all_in(self):
        """
        Test the spatial query to get geounits within a known boundary.
        """
        level = self.geolevels[0]
        units = self.geounits[level.id]

        units = Geounit.objects.filter(geom__within=units[0].geom,geolevel__gt=level.id)

        numunits = len(units)
        self.assertEquals(90, numunits, 'Number of geounits within a high-level geounit is incorrect. (%d)' % numunits)

    def test_get_in_gu0(self):
        """
        Test the spatial query to get geounits within a known boundary.
        """
        level = self.geolevels[0]
        units = self.geounits[level.id]

        units = Geounit.objects.filter(geom__within=units[0].geom,geolevel=level.id+1)
        numunits = len(units)
        self.assertEquals(9, numunits, 'Number of geounits within geounit 1 is incorrect. (%d)' % numunits)

    def test_get_base(self):
        """
        Test the spatial query to get all geounits at the base geolevel within a boundary.
        """
        level = self.legbod.get_geolevels()[0]
        units = self.geounits[level.id]
        geounit_ids = tuple([units[0].id, units[1].id])
        base_level = self.legbod.get_base_geolevel()


        units = Geounit.objects.filter(geom__within=units[0].geom,geolevel=base_level)

        numunits = len(units)
        self.assertEquals(81, numunits, 'Number of geounits within a high-level geounit is incorrect. (%d)' % numunits)

    def test_get_mixed1(self):
        """
        Test the logic for getting mixed geounits inside a boundary at the
        highest geolevel.
        """
        level = self.geolevels[0]
        bigunits = self.geounits[level.id]
        ltlunits = self.geounits[self.geolevels[1].id]
        boundary = bigunits[0].geom.difference(ltlunits[9].geom)

        units = Geounit.get_mixed_geounits([str(bigunits[0].id)], self.legbod, level.id, boundary, True)
        numunits = len(units)
        self.assertEquals(8, numunits, 'Number of geounits inside boundary is incorrect. (%d)' % numunits)

    def test_get_imixed1(self):
        """
        Test the logic for getting mixed geounits outside a boundary at the
        highest geolevel.
        """
        level = self.geolevels[0]
        bigunits = self.geounits[level.id]
        ltlunits = self.geounits[self.geolevels[1].id]
        boundary = bigunits[0].geom.difference(ltlunits[9].geom)

        units = Geounit.get_mixed_geounits([str(bigunits[0].id)], self.legbod, level.id, boundary, False)
        numunits = len(units)
        self.assertEquals(1, numunits, 'Number of geounits outside boundary is incorrect. (%d)' % numunits)

    def test_get_mixed2(self):
        """
        Test the logic for getting mixed geounits inside a boundary at the
        middle geolevel.
        """
        level = self.geolevels[1]
        bigunits = self.geounits[level.id]
        ltlunits = self.geounits[self.geolevels[2].id]
        boundary = bigunits[0].geom.difference(ltlunits[27].geom)

        units = Geounit.get_mixed_geounits([str(bigunits[0].id)], self.legbod, level.id, boundary, True)
        numunits = len(units)
        self.assertEquals(8, numunits, 'Number of geounits inside boundary is incorrect. (%d)' % numunits)

    def test_get_imixed2(self):
        """
        Test the logic for getting mixed geounits outside a boundary at the
        middle geolevel.
        """
        level = self.geolevels[1]
        bigunits = self.geounits[level.id]
        ltlunits = self.geounits[self.geolevels[2].id]
        boundary = bigunits[0].geom.difference(ltlunits[27].geom)

        units = Geounit.get_mixed_geounits([str(bigunits[0].id)], self.legbod, level.id, boundary, False)
        numunits = len(units)
        self.assertEquals(1, numunits, 'Number of geounits outside boundary is incorrect. (%d)' % numunits)

    def test_get_mixed3(self):
        """
        Test the logic for getting mixed geounits inside a boundary at the
        lowest geolevel.
        """
        level = self.geolevels[0]
        bigunits = self.geounits[level.id]
        boundary = MultiPolygon(Polygon(LinearRing(
            Point((0,0)),
            Point((1,0)),
            Point((1,1)),
            Point((0,0))
        )))
        boundary.srid = 3785
        
        units = Geounit.get_mixed_geounits([str(bigunits[1].id), str(bigunits[2].id), str(bigunits[5].id)], self.legbod, level.id, boundary, True)
        numunits = len(units)
        self.assertEquals(3, numunits, 'Number of geounits inside boundary is incorrect. (%d)' % numunits)

        units = Geounit.get_mixed_geounits([str(bigunits[0].id),str(bigunits[4].id),str(bigunits[8].id)], self.legbod, level.id, boundary, True)
        numunits = len(units)
        self.assertEquals(63, numunits, 'Number of geounits inside boundary is incorrect. (%d)' % numunits)

    def test_get_imixed3(self):
        """
        Test the logic for getting mixed geounits outside a boundary at the
        lowest geolevel.
        """
        level = self.geolevels[0]
        bigunits = self.geounits[level.id]
        boundary = MultiPolygon(Polygon(LinearRing(
            Point((0,0)),
            Point((1,0)),
            Point((1,1)),
            Point((0,0))
        )))
        boundary.srid = 3785
        
        units = Geounit.get_mixed_geounits([str(bigunits[3].id),str(bigunits[6].id),str(bigunits[7].id)], self.legbod, level.id, boundary, False)
        numunits = len(units)
        # this test should return 3, for the large geounits are completely
        # without yet intersect at the corner. the net geometry from this
        # set of mixed geounits is correct, though
        self.assertEquals(19, numunits, 'Number of geounits outside boundary is incorrect. (%d)' % numunits)

        units = Geounit.get_mixed_geounits([str(bigunits[0].id),str(bigunits[4].id),str(bigunits[8].id)], self.legbod, level.id, boundary, False)
        numunits = len(units)
        self.assertEquals(63, numunits, 'Number of geounits outside boundary is incorrect. (%d)' % numunits)


class PurgeTestCase(BaseTestCase):
    """
    Unit tests to test the methods for purging extra districts off a plan.
    """
    def setUp(self):
        BaseTestCase.setUp(self)

        # create a new buch of districts for this test case
        self.plan.district_set.all().delete()

        geolevelid = self.geolevels[1].id

        # create Districts
        for i in range(0,9):
            start = 9 * i
            end = 9 * (i + 1)

            # overlap the previous assignment to create multiple versions
            # of districts
            if i > 0:
                start -= 1
            if i < 8:
                end += 1

            geounits = self.geounits[geolevelid][start:end]
            geounits = map(lambda x: str(x.id), geounits)
       
            self.plan.add_geounits( (i+1), geounits, geolevelid, self.plan.version)

    def test_purge_lt_zero(self):
        self.plan.purge(before=-1)

        self.assertEquals(9, self.plan.version, 'Plan version is incorrect.')
        count = self.plan.district_set.count()
        self.assertEquals(17, count, 'Number of districts in plan is incorrect. (e:17,a:%d)' % count)
        
    def test_purge_gt_max(self):
        self.plan.purge(after=9)

        self.assertEquals(9, self.plan.version, 'Plan version is incorrect.')
        count = self.plan.district_set.count()
        self.assertEquals(17, count, 'Number of districts in plan is incorrect. (e:17,a:%d)' % count)

    def test_purge_lt_four(self):
        self.plan.purge(before=4)

        self.assertEquals(9, self.plan.version, 'Plan version is incorrect.')

        # should have 13 items, purging old versions of districts at version
        # 0, 1, 2, and 3 but keeping the most recent version of each 
        # district 
        # (even if the district version is less than the 'before' keyword)
        count = self.plan.district_set.count()
        self.assertEquals(13, count, 'Number of districts in plan is incorrect. (e:13, a:%d)' % count)

    def test_purge_lt_nine(self):
        self.plan.purge(before=9)

        self.assertEquals(9, self.plan.version, 'Plan version is incorrect.')

        # should have 9 items, purging all old versions of districts, but 
        # keeping the most recent version of each district 
        # (even if the district version is less than the 'before' keyword)
        count = self.plan.district_set.count()
        self.assertEquals(9, count, 'Number of districts in plan is incorrect. (e:9, a:%d)' % count)

    def test_purge_gt_five(self):
        self.plan.purge(after=5)

        self.assertEquals(9, self.plan.version, 'Plan version is incorrect.')

        # should have 9 items, since everything after version 5 was deleted
        # 2 of District 1
        # 2 of District 2
        # 2 of District 3
        # 2 of District 4
        # 1 of District 5
        count = self.plan.district_set.count()
        self.assertEquals(9, count, 'Number of districts in plan is incorrect. (e:9, a:%d)' % count)

    def test_purge_many_edits(self):
        geolevelid = self.geolevels[1].id

        oldversion = self.plan.version

        count = self.plan.district_set.count()

        # every add_geounits call should add 2 districts to the 
        # district_set, since this geounit should be removed from one
        # district, and added to another.
        for i in range(0,8):
            item = 9 * (i + 1) + 1

            item = str(self.geounits[geolevelid][item].id)
            self.plan.add_geounits( (i+1), [item], geolevelid, self.plan.version)

        # net gain: 16 districts

        self.assertEquals(16, self.plan.district_set.count() - count, 'Incorrect of districts in the plan district_set.')
        self.assertEquals(8, self.plan.version-oldversion, 'Incorrect number of versions incremented after 8 edits.')

        self.plan.purge(before=oldversion)

        # net loss: 16 districts

        count = self.plan.district_set.count()
        self.assertEquals(16, count, 'Number of districts in plan is incorrect. (e:16, a:%d)' % count)

    def test_version_back(self):
        version = self.plan.get_nth_previous_version(self.plan.version)

        self.assertEquals(0, version, 'Walking back %d versions does not land at zero.' % self.plan.version)

        version = self.plan.get_nth_previous_version(self.plan.version-1)

        self.assertEquals(1, version, 'Walking back %d versions does not land at one.' % (self.plan.version - 1))

    def test_purge_versions(self):
        geolevelid = self.geolevels[1].id

        oldversion = self.plan.version
        for i in range(oldversion - 1, 4, -1):
            item = 9 * (i + 1) - 2;
            item = str(self.geounits[geolevelid][item].id)
            self.plan.add_geounits( (i+1), [item], geolevelid, i)

        # added four new versions

        newversion = self.plan.version
        self.assertEquals(13, newversion, 'Adding items to sequential positions in history resulted in the wrong number of versions. (e:17,a:%d)' % newversion)

        # the first step back in history shoulde be version 4, since the
        # last edit was off that version

        previous = self.plan.get_nth_previous_version(1)
        self.assertEquals(5, previous, 'The previous version is incorrect, since edits were performed off of 8,7,6,5 versions, with the last edit being off of version 5. (e:5, a:%d)' % previous)

        previous = self.plan.get_nth_previous_version(3)
        self.assertEquals(3, previous, '(e:3, a:%d)' % previous)

        previous = self.plan.get_nth_previous_version(5)
        self.assertEquals(1, previous, '(e:1, a:%d)' % previous)

class CalculatorCase(BaseTestCase):
    def test_sum1(self):
        sum1 = Sum()
        sum1.arg_dict['value1'] = ('literal','10',)
        sum1.arg_dict['value2'] = ('literal','20',)

        self.assertEquals(None,sum1.result)
        sum1.compute(district=self.district1)
        self.assertEquals(30,sum1.result)

        sum2 = Sum()

        self.assertEquals(None,sum2.result)
        self.assertEquals(30,sum1.result)

        sum2.compute(district=self.district1)

        self.assertEquals(0,sum2.result)
        self.assertEquals(30,sum1.result)
        
    def test_sum2a(self):
        sumcalc = Sum()
        sumcalc.arg_dict['value1'] = ('literal','0',)
        sumcalc.arg_dict['value2'] = ('literal','1',)
        sumcalc.arg_dict['value3'] = ('literal','2',)
        sumcalc.compute(plan=self.plan)

        # The sum of a plan w/3 districts and w/3 literals is the sum
        # of literals * the number of plans

        self.assertEquals(9, sumcalc.result, 'Incorrect value during summation. (e:%d,a:%d)' % (9, sumcalc.result))

    def test_sum2b(self):
        sumcalc = Sum()
        sumcalc.arg_dict['value1'] = ('literal','0',)
        sumcalc.arg_dict['value2'] = ('literal','1',)
        sumcalc.arg_dict['value3'] = ('literal','2',)
        sumcalc.compute(district=self.district1)

        self.assertEquals(3, sumcalc.result, 'Incorrect value during summation. (e:%d,a:%d)' % (3, sumcalc.result))

    def test_sum3(self):
        geolevelid = self.geolevels[1].id
        geounits = self.geounits[geolevelid]

        dist1ids = geounits[0:3] + geounits[9:12]
        exqset = Characteristic.objects.filter(geounit__in=dist1ids,subject=self.subject1)
        expected = float(exqset.aggregate(SumAgg('number'))['number__sum']) + 5.0

        dist1ids = map(lambda x: str(x.id), dist1ids)
        
        self.plan.add_geounits( self.district1.district_id, dist1ids, geolevelid, self.plan.version)
        district1 = self.plan.district_set.get(district_id=self.district1.district_id,version=self.plan.version)

        sumcalc = Sum()
        sumcalc.arg_dict['value1'] = ('subject',self.subject1.name,)
        sumcalc.arg_dict['value2'] = ('literal','5.0',)
        sumcalc.compute(district=district1)

        actual = sumcalc.result

        self.assertEquals(expected, actual, 'Incorrect value during summation. (e:%d,a:%d)' % (expected, actual))

    def test_sum4(self):
        geolevelid = self.geolevels[1].id
        geounits = self.geounits[geolevelid]

        dist1ids = geounits[0:3] + geounits[9:12]
        exqset = Characteristic.objects.filter(geounit__in=dist1ids,subject=self.subject1)
        expected = float(exqset.aggregate(SumAgg('number'))['number__sum'])

        dist1ids = map(lambda x: str(x.id), dist1ids)
        
        self.plan.add_geounits( self.district1.district_id, dist1ids, geolevelid, self.plan.version)
        district1 = self.plan.district_set.get(district_id=self.district1.district_id,version=self.plan.version)

        sumcalc = Sum()
        sumcalc.arg_dict['value1'] = ('subject',self.subject1.name,)
        sumcalc.compute(district=district1)

        actual = sumcalc.result

        self.assertEquals(expected, actual, 'Incorrect value during summation. (e:%d,a:%d)' % (expected, actual))

    def test_sum5(self):
        geolevelid = self.geolevels[1].id
        geounits = self.geounits[geolevelid]

        dist1ids = geounits[0:3] + geounits[9:12]
        dist2ids = geounits[18:21] + geounits[27:30] + geounits[36:39]
        exqset = Characteristic.objects.filter(geounit__in=dist1ids+dist2ids,subject=self.subject1)
        expected = float(exqset.aggregate(SumAgg('number'))['number__sum'])

        dist1ids = map(lambda x: str(x.id), dist1ids)
        dist2ids = map(lambda x: str(x.id), dist2ids)
        
        self.plan.add_geounits( self.district1.district_id, dist1ids, geolevelid, self.plan.version)
        self.plan.add_geounits( self.district2.district_id, dist2ids, geolevelid, self.plan.version)

        sumcalc = Sum()
        sumcalc.arg_dict['value1'] = ('subject',self.subject1.name,)
        sumcalc.compute(plan=self.plan)

        actual = sumcalc.result

        self.assertEquals(expected, actual, 'Incorrect value during summation. (e:%d,a:%d)' % (expected, actual))


    def test_percent1(self):
        pctcalc = Percent()
        pctcalc.arg_dict['numerator'] = ('literal','1',)
        pctcalc.arg_dict['denominator'] = ('literal','2',)
        pctcalc.compute(district=self.district1)

        self.assertEquals(0.5, pctcalc.result, 'Incorrect value during percentage. (e:%d,a:%d)' % (0.5, pctcalc.result))

    def test_percent2(self):
        pctcalc = Percent()
        pctcalc.arg_dict['numerator'] = ('literal','2',)
        pctcalc.arg_dict['denominator'] = ('literal','4',)
        pctcalc.compute(district=self.district1)

        self.assertEquals(0.5, pctcalc.result, 'Incorrect value during percentage. (e:%d,a:%d)' % (0.5, pctcalc.result))

    def test_percent3(self):
        geolevelid = self.geolevels[1].id
        geounits = self.geounits[geolevelid]

        dist1ids = geounits[0:3] + geounits[9:12]
        exqset = Characteristic.objects.filter(geounit__in=dist1ids,subject=self.subject1)
        expected = float(exqset.aggregate(SumAgg('number'))['number__sum']) / 10.0

        dist1ids = map(lambda x: str(x.id), dist1ids)
        
        self.plan.add_geounits( self.district1.district_id, dist1ids, geolevelid, self.plan.version)
        district1 = self.plan.district_set.get(district_id=self.district1.district_id,version=self.plan.version)

        pctcalc = Percent()
        pctcalc.arg_dict['numerator'] = ('subject',self.subject1.name,)
        pctcalc.arg_dict['denominator'] = ('literal','10.0',)
        pctcalc.compute(district=district1)

        actual = pctcalc.result

        self.assertEquals(expected, actual, 'Incorrect value during percentage. (e:%f,a:%f)' % (expected, actual))

    def test_percent4(self):
        geolevelid = self.geolevels[1].id
        geounits = self.geounits[geolevelid]

        dist1ids = geounits[0:3] + geounits[9:12]
        dist2ids = geounits[18:21] + geounits[27:30] + geounits[36:39]
        exqset = Characteristic.objects.filter(geounit__in=dist1ids+dist2ids,subject=self.subject1)
        expected = float(exqset.aggregate(SumAgg('number'))['number__sum']) / 20.0

        dist1ids = map(lambda x: str(x.id), dist1ids)
        dist2ids = map(lambda x: str(x.id), dist2ids)
        
        self.plan.add_geounits( self.district1.district_id, dist1ids, geolevelid, self.plan.version)
        self.plan.add_geounits( self.district2.district_id, dist2ids, geolevelid, self.plan.version)

        pctcalc = Percent()
        pctcalc.arg_dict['numerator'] = ('subject',self.subject1.name,)
        pctcalc.arg_dict['denominator'] = ('literal','10.0',)
        pctcalc.compute(plan=self.plan)

        actual = pctcalc.result

        self.assertEquals(expected, actual, 'Incorrect value during percentage. (e:%f,a:%f)' % (expected, actual))

    def test_percent5(self):
        geolevelid = self.geolevels[1].id
        geounits = self.geounits[geolevelid]

        dist1ids = geounits[0:3] + geounits[9:12]
        dist2ids = geounits[18:21] + geounits[27:30] + geounits[36:39]
        dist1ids = map(lambda x: str(x.id), dist1ids)
        dist2ids = map(lambda x: str(x.id), dist2ids)
        
        self.plan.add_geounits( self.district1.district_id, dist1ids, geolevelid, self.plan.version)
        self.plan.add_geounits( self.district2.district_id, dist2ids, geolevelid, self.plan.version)

        pctcalc = Percent()
        pctcalc.arg_dict['numerator'] = ('subject',self.subject1.name,)
        pctcalc.arg_dict['denominator'] = ('subject',self.subject1.name,)
        pctcalc.compute(plan=self.plan)

        actual = pctcalc.result

        self.assertEquals(1.0, actual, 'Incorrect value during percentage. (e:%f,a:%f)' % (1.0, actual))


    def test_threshold1(self):
        thrcalc = Threshold()
        thrcalc.arg_dict['value'] = ('literal','1',)
        thrcalc.arg_dict['threshold'] = ('literal','2',)
        thrcalc.compute(district=self.district1)

        self.assertEquals(0, thrcalc.result, 'Incorrect value during threshold. (e:%s,a:%s)' % (0, thrcalc.result))

    def test_threshold2(self):
        thrcalc = Threshold()
        thrcalc.arg_dict['value'] = ('literal','2',)
        thrcalc.arg_dict['threshold'] = ('literal','1',)
        thrcalc.compute(district=self.district1)

        self.assertEquals(1, thrcalc.result, 'Incorrect value during threshold. (e:%s,a:%s)' % (1, thrcalc.result))

    def test_threshold3(self):
        geolevelid = self.geolevels[1].id
        geounits = self.geounits[geolevelid]

        dist1ids = geounits[0:3] + geounits[9:12]
        exqset = Characteristic.objects.filter(geounit__in=dist1ids,subject=self.subject1)
        expected = float(exqset.aggregate(SumAgg('number'))['number__sum']) > 10.0
        expected = 1 if expected else 0

        dist1ids = map(lambda x: str(x.id), dist1ids)
        
        self.plan.add_geounits( self.district1.district_id, dist1ids, geolevelid, self.plan.version)
        district1 = self.plan.district_set.get(district_id=self.district1.district_id,version=self.plan.version)

        thrcalc = Threshold()
        thrcalc.arg_dict['value'] = ('subject',self.subject1.name,)
        thrcalc.arg_dict['threshold'] = ('literal','10.0',)
        thrcalc.compute(district=district1)

        actual = thrcalc.result

        self.assertEquals(expected, actual, 'Incorrect value during threshold. (e:%s,a:%s)' % (expected, actual))

    def test_threshold4(self):
        geolevelid = self.geolevels[1].id
        geounits = self.geounits[geolevelid]

        dist1ids = geounits[0:3] + geounits[9:12]
        exqset = Characteristic.objects.filter(geounit__in=dist1ids,subject=self.subject1)
        expected = float(exqset.aggregate(SumAgg('number'))['number__sum']) > 5.0
        expected = 1 if expected else 0

        dist1ids = map(lambda x: str(x.id), dist1ids)
        
        self.plan.add_geounits( self.district1.district_id, dist1ids, geolevelid, self.plan.version)
        district1 = self.plan.district_set.get(district_id=self.district1.district_id,version=self.plan.version)

        thrcalc = Threshold()
        thrcalc.arg_dict['value'] = ('subject',self.subject1.name,)
        thrcalc.arg_dict['threshold'] = ('literal','5.0',)
        thrcalc.compute(district=district1)

        actual = thrcalc.result

        self.assertEquals(expected, actual, 'Incorrect value during threshold. (e:%s,a:%s)' % (expected, actual))

    def test_range1(self):
        rngcalc = Range()
        rngcalc.arg_dict['value'] = ('literal','2',)
        rngcalc.arg_dict['min'] = ('literal','1',)
        rngcalc.arg_dict['max'] = ('literal','3',)
        rngcalc.compute(district=self.district1)

        self.assertEquals(1, rngcalc.result, 'Incorrect value during range. (e:%s,a:%s)' % (1, rngcalc.result))

    def test_range2(self):
        rngcalc = Range()
        rngcalc.arg_dict['value'] = ('literal','1',)
        rngcalc.arg_dict['min'] = ('literal','2',)
        rngcalc.arg_dict['max'] = ('literal','3',)
        rngcalc.compute(district=self.district1)

        self.assertEquals(0, rngcalc.result, 'Incorrect value during range. (e:%s,a:%s)' % (0, rngcalc.result))

    def test_range3(self):
        geolevelid = self.geolevels[1].id
        geounits = self.geounits[geolevelid]

        dist1ids = geounits[0:3] + geounits[9:12]
        exqset = Characteristic.objects.filter(geounit__in=dist1ids,subject=self.subject1)
        expected = float(exqset.aggregate(SumAgg('number'))['number__sum'])
        expected = 1 if 5.0 < expected and expected < 10.0 else 0

        dist1ids = map(lambda x: str(x.id), dist1ids)
        
        self.plan.add_geounits( self.district1.district_id, dist1ids, geolevelid, self.plan.version)
        district1 = self.plan.district_set.get(district_id=self.district1.district_id,version=self.plan.version)

        rngcalc = Range()
        rngcalc.arg_dict['value'] = ('subject',self.subject1.name,)
        rngcalc.arg_dict['min'] = ('literal','5.0',)
        rngcalc.arg_dict['max'] = ('literal','10.0',)
        rngcalc.compute(district=district1)

        actual = rngcalc.result

        self.assertEquals(expected, actual, 'Incorrect value during range. (e:%s,a:%s)' % (expected, actual))

    def test_range4(self):
        geolevelid = self.geolevels[1].id
        geounits = self.geounits[geolevelid]

        dist1ids = geounits[0:3] + geounits[9:12]
        exqset = Characteristic.objects.filter(geounit__in=dist1ids,subject=self.subject1)
        expected = float(exqset.aggregate(SumAgg('number'))['number__sum'])
        expected = 1 if 1.0 < expected and expected < 5.0 else 0

        dist1ids = map(lambda x: str(x.id), dist1ids)
        
        self.plan.add_geounits( self.district1.district_id, dist1ids, geolevelid, self.plan.version)
        district1 = self.plan.district_set.get(district_id=self.district1.district_id,version=self.plan.version)

        rngcalc = Range()
        rngcalc.arg_dict['value'] = ('subject',self.subject1.name,)
        rngcalc.arg_dict['min'] = ('literal','1.0',)
        rngcalc.arg_dict['max'] = ('literal','5.0',)
        rngcalc.compute(district=district1)

        actual = rngcalc.result

        self.assertEquals(expected, actual, 'Incorrect value during range. (e:%s,a:%s)' % (expected, actual))

    def test_contiguity1(self):
        cntcalc = Contiguity()
        cntcalc.compute(district=self.district1)

        self.assertEquals(0, cntcalc.result, 'District is contiguous.')

    def test_contiguity2(self):
        geolevelid = self.geolevels[1].id
        geounits = self.geounits[geolevelid]

        dist1ids = geounits[0:3] + geounits[12:15]
        dist1ids = map(lambda x: str(x.id), dist1ids)
        
        self.plan.add_geounits( self.district1.district_id, dist1ids, geolevelid, self.plan.version)
        district1 = self.plan.district_set.get(district_id=self.district1.district_id,version=self.plan.version)

        cntcalc = Contiguity()
        cntcalc.compute(district=district1)

        self.assertEquals(0, cntcalc.result, 'District is contiguous.')

    def test_contiguity3(self):
        geolevelid = self.geolevels[1].id
        geounits = self.geounits[geolevelid]

        dist1ids = geounits[0:3] + geounits[9:12]
        dist1ids = map(lambda x: str(x.id), dist1ids)
        
        self.plan.add_geounits( self.district1.district_id, dist1ids, geolevelid, self.plan.version)
        district1 = self.plan.district_set.get(district_id=self.district1.district_id,version=self.plan.version)

        cntcalc = Contiguity()
        cntcalc.compute(district=district1)

        self.assertEquals(1, cntcalc.result, 'District is discontiguous.')

    def test_equivalence1(self):
        geolevelid = self.geolevels[1].id
        geounits = self.geounits[geolevelid]

        dist1ids = geounits[0:3] + geounits[9:12]
        dist2ids = geounits[18:21] + geounits[27:30] + geounits[36:39]
        dist1ids = map(lambda x: str(x.id), dist1ids)
        dist2ids = map(lambda x: str(x.id), dist2ids)
        
        self.plan.add_geounits( self.district1.district_id, dist1ids, geolevelid, self.plan.version)
        self.plan.add_geounits( self.district2.district_id, dist2ids, geolevelid, self.plan.version)

        equcalc = Equivalence()
        equcalc.arg_dict['value'] = ('subject',self.subject1.name,)
        equcalc.compute(plan=self.plan)

        actual = equcalc.result

        self.assertEquals(3.0, actual, 'Incorrect value during equivalence. (e:%f,a:%f)' % (1.0, actual))


    def test_partisandiff1(self):
        geolevelid = self.geolevels[1].id
        geounits = self.geounits[geolevelid]

        dist1ids = geounits[0:3] + geounits[9:12]
        dist2ids = geounits[6:9] + geounits[15:18]
        dist1ids = map(lambda x: str(x.id), dist1ids)
        dist2ids = map(lambda x: str(x.id), dist2ids)
        
        self.plan.add_geounits( self.district1.district_id, dist1ids, geolevelid, self.plan.version)
        self.plan.add_geounits( self.district2.district_id, dist2ids, geolevelid, self.plan.version)

        district1 = self.plan.district_set.filter(district_id=self.district1.district_id, version=self.plan.version-1)[0]

        pdcalc = PartisanDifferential()
        pdcalc.arg_dict['democratic'] = ('subject',self.subject1.name,)
        pdcalc.arg_dict['republican'] = ('subject',self.subject2.name,)
        pdcalc.compute(district=district1)

        actual = pdcalc.result

        self.assertAlmostEquals(0.923077, actual, 6, 'Incorrect value during partisan differential. (e:%f,a:%f)' % (0.923077, actual))

        district2 = self.plan.district_set.filter(district_id=self.district2.district_id, version=self.plan.version)[0]

        pdcalc.arg_dict['democratic'] = ('subject',self.subject2.name,)
        pdcalc.arg_dict['republican'] = ('subject',self.subject1.name,)
        pdcalc.compute(district=district2)

        actual = pdcalc.result

        self.assertAlmostEquals(0.461538, actual, 6, 'Incorrect value during partisan differential. (e:%f,a:%f)' % (0.461538, actual))

    def test_partisandiff2(self):
        geolevelid = self.geolevels[1].id
        geounits = self.geounits[geolevelid]

        dist1ids = geounits[0:3] + geounits[9:12]
        dist2ids = geounits[6:9] + geounits[15:18]
        dist1ids = map(lambda x: str(x.id), dist1ids)
        dist2ids = map(lambda x: str(x.id), dist2ids)
        
        self.plan.add_geounits( self.district1.district_id, dist1ids, geolevelid, self.plan.version)
        self.plan.add_geounits( self.district2.district_id, dist2ids, geolevelid, self.plan.version)

        pdcalc = PartisanDifferential()
        pdcalc.arg_dict['democratic'] = ('subject',self.subject1.name,)
        pdcalc.arg_dict['republican'] = ('subject',self.subject2.name,)
        pdcalc.compute(plan=self.plan)

        actual = pdcalc.result
        expected = (0.923077 + 0.461538) / 2

        self.assertAlmostEquals(expected, actual, 6, 'Incorrect value during partisan differential. (e:%f,a:%f)' % (expected, actual))

    def test_repfairness1(self):
        geolevelid = self.geolevels[1].id
        geounits = self.geounits[geolevelid]

        dist1ids = geounits[0:3] + geounits[9:12]
        dist2ids = geounits[6:9] + geounits[15:18]
        dist1ids = map(lambda x: str(x.id), dist1ids)
        dist2ids = map(lambda x: str(x.id), dist2ids)
        
        self.plan.add_geounits( self.district1.district_id, dist1ids, geolevelid, self.plan.version)
        self.plan.add_geounits( self.district2.district_id, dist2ids, geolevelid, self.plan.version)

        rfcalc = RepresentationalFairness()
        rfcalc.arg_dict['democratic'] = ('subject',self.subject1.name,)
        rfcalc.arg_dict['republican'] = ('subject',self.subject2.name,)
        rfcalc.compute(plan=self.plan)

        actual = rfcalc.result

        self.assertEquals(1.0, actual, 'Incorrect value during representational fairness. (e:%f,a:%f)' % (1.0, actual))

    def test_repfairness2(self):
        geolevelid = self.geolevels[1].id
        geounits = self.geounits[geolevelid]

        dist1ids = geounits[0:3] + geounits[9:12]
        dist2ids = geounits[6:9] + geounits[15:18]
        dist1ids = map(lambda x: str(x.id), dist1ids)
        dist2ids = map(lambda x: str(x.id), dist2ids)
        
        self.plan.add_geounits( self.district1.district_id, dist1ids, geolevelid, self.plan.version)
        self.plan.add_geounits( self.district2.district_id, dist2ids, geolevelid, self.plan.version)

        rfcalc = RepresentationalFairness()
        rfcalc.arg_dict['democratic'] = ('subject',self.subject2.name,)
        rfcalc.arg_dict['republican'] = ('subject',self.subject1.name,)
        rfcalc.compute(plan=self.plan)

        actual = rfcalc.result

        self.assertAlmostEquals(0.181818, actual, 6, 'Incorrect value during representational fairness. (e:%f,a:%f)' % (0.181818, actual))
